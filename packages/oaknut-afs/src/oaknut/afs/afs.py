"""The ``AFS`` handle — public entry point to an AFS region.

An :class:`AFS` wraps a :class:`oaknut.discimage.UnifiedDisc` plus the
two info-sector addresses (``sec1``, ``sec2``) installed by WFSINIT
in the host ADFS map. It knows how to read its own info sector, the
root directory, and any file reachable from it — the end-to-end read
path delivered in phase 6.

Two entry points exist:

- :meth:`AFS.from_file` opens a host disc image via ``ADFS.from_file``,
  reads the AFS info-sector pointers through the ADFS old map, and
  yields an AFS handle. The ADFS context manager stays active for the
  life of the AFS session — the two share one underlying
  :class:`UnifiedDisc`, so writes through either see the same bytes.
- :meth:`oaknut.adfs.ADFS.afs_partition` is the natural entry point
  when the caller is already working with ADFS and wants to reach
  the tail-cylinder AFS region without reopening the file.

The read path is organised as a set of small, composable primitives
around :class:`~oaknut.afs.map_sector.MapSector` and
:class:`~oaknut.afs.directory.AfsDirectory`. ``_resolve`` walks a
path from the root by dereferencing each name through its parent
directory; ``_read_object_bytes`` streams a map sector's data through
:class:`~oaknut.afs.map_sector.ExtentStream`.

Phase 6 is read-only. The ``writable`` and ``flush`` affordances
described in the plan are stubbed out as no-ops so they can be
exercised by tests now and carry real semantics from phase 9 onward.
"""

from __future__ import annotations

from contextlib import contextmanager
from os import PathLike
from typing import TYPE_CHECKING, Iterator, Union

from oaknut.afs.directory import (
    AfsDirectory,
    DirectoryEntry,
    grow_directory_bytes,
    insert_entry,
)
from oaknut.afs.exceptions import (
    AFSDirectoryFullError,
    AFSError,
    AFSInfoSectorError,
    AFSPathError,
)
from oaknut.afs.info_sector import INFO_SECTOR_SIZE, InfoSector, InfoSectorPair
from oaknut.afs.map_sector import (
    _MAX_DATA_EXTENTS,
    MAP_SECTOR_SIZE,
    Extent,
    ExtentStream,
    MapChain,
    MapSector,
)
from oaknut.afs.passwords import PASSWORDS_FILENAME, PasswordsFile
from oaknut.afs.path import AFSPath
from oaknut.afs.types import Geometry, SystemInternalName

#: Directory grow step: one disc block, matching ``CHZSZE`` at
#: ``Uade0E.asm:1167`` which adds exactly ``BLKSZE = 256`` bytes each
#: time an insert fails with an empty free list.
_DIRECTORY_GROW_STEP_BYTES = 256

#: Maximum directory size, from ``MAXDIR`` at ``Uade02.asm:158``
#: (= 26 disc blocks = 6656 bytes, enough for 255 slots).
_MAX_DIRECTORY_BYTES = 26 * 256

if TYPE_CHECKING:
    from oaknut.discimage.unified_disc import UnifiedDisc


class AFSNotPresentError(AFSError):
    """Raised when a caller asks for AFS on a disc that has no AFS pointers."""


class AFS:
    """Open handle on an Acorn Level 3 File Server filesystem region.

    Instances are normally obtained through :meth:`AFS.from_file` or
    via ``ADFS.afs_partition``. The constructor is public but low
    level: callers must supply the two info-sector addresses from
    the host map themselves.
    """

    def __init__(
        self,
        unified_disc: "UnifiedDisc",
        sec1: int,
        sec2: int,
        *,
        user: str = "Syst",
        enforce_quota: bool = True,
    ) -> None:
        if sec1 <= 0 or sec2 <= 0:
            raise AFSNotPresentError(
                f"AFS info-sector pointers are zero (sec1={sec1}, sec2={sec2}); "
                "disc has no AFS partition"
            )
        self._disc = unified_disc
        self._sec1 = sec1
        self._sec2 = sec2
        # Write-back buffer must be initialised before _read_and_verify_info
        # because _read_sector checks it.
        self._pending_writes: dict[int, bytes] = {}
        self._info: InfoSector = self._read_and_verify_info()
        self._passwords_cache: PasswordsFile | None = None
        self._bitmap_shadow_cache = None
        self._allocator_cache = None
        self._acting_user: str = user
        self._enforce_quota: bool = enforce_quota

    # ------------------------------------------------------------------
    # Named constructors
    # ------------------------------------------------------------------

    @staticmethod
    @contextmanager
    def from_file(filepath: Union[str, PathLike]) -> Iterator[AFS]:
        """Open a disc image and yield the AFS partition as a context manager.

        Opens the image first as ADFS (reusing its sector-access and
        geometry detection), then reaches the AFS partition through
        :attr:`oaknut.adfs.ADFS.afs_partition`. Raises
        :class:`AFSNotPresentError` if the disc has no AFS pointers.

        The host ADFS context manager stays active for the duration
        of the yielded block; on exit, any mutations flush through
        the same :class:`UnifiedDisc` the ADFS handle owns.
        """
        # Deferred import to avoid a hard module-level import cycle
        # between oaknut-afs and oaknut-adfs during test collection.
        from oaknut.adfs import ADFS

        with ADFS.from_file(filepath) as adfs:
            afs = adfs.afs_partition
            if afs is None:
                raise AFSNotPresentError(
                    f"{filepath} has no AFS partition (no info-sector pointers)"
                )
            yield afs

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def info_sector(self) -> InfoSector:
        """The validated :class:`InfoSector` for this region."""
        return self._info

    @property
    def disc_name(self) -> str:
        return self._info.disc_name

    @property
    def geometry(self) -> Geometry:
        return Geometry(
            cylinders=self._info.cylinders,
            sectors_per_cylinder=self._info.sectors_per_cylinder,
            total_sectors=self._info.total_sectors,
            bitmap_size_sectors=self._info.bitmap_size_sectors,
        )

    @property
    def start_cylinder(self) -> int:
        return self._info.start_cylinder

    @property
    def root(self) -> AFSPath:
        """The root directory path ``$`` bound to this handle."""
        return AFSPath._bound_root(self)

    @property
    def users(self) -> PasswordsFile:
        """Parsed ``$.Passwords`` file, read lazily and cached."""
        if self._passwords_cache is None:
            self._passwords_cache = self._load_passwords()
        return self._passwords_cache

    @property
    def free_sectors(self) -> int:
        """Total free data sectors across all cylinders in the region."""
        shadow = self._bitmap_shadow()
        return shadow.total_free()

    # ------------------------------------------------------------------
    # Read primitives
    # ------------------------------------------------------------------

    def _read_sector(self, sector: int) -> bytes:
        """Read one 256-byte sector by absolute address.

        Checks the write-back buffer first; if the sector has been
        written but not yet flushed, the buffered copy is returned
        instead of reading from the underlying disc.
        """
        if sector in self._pending_writes:
            return self._pending_writes[sector]
        if sector < 0 or sector >= self._disc.num_sectors:
            raise AFSError(
                f"sector {sector:#x} outside disc range 0..{self._disc.num_sectors - 1:#x}"
            )
        view = self._disc.sector_range(sector, 1)
        data = bytes(view[:])
        if len(data) != MAP_SECTOR_SIZE:
            raise AFSError(
                f"short read at sector {sector:#x}: got {len(data)} bytes, "
                f"expected {MAP_SECTOR_SIZE}"
            )
        return data

    def _read_and_verify_info(self) -> InfoSector:
        primary_bytes = self._read_sector(self._sec1)
        secondary_bytes = self._read_sector(self._sec2)
        if len(primary_bytes) < INFO_SECTOR_SIZE or len(secondary_bytes) < INFO_SECTOR_SIZE:
            raise AFSInfoSectorError(
                "info sector reads returned short data "
                f"(primary={len(primary_bytes)}, secondary={len(secondary_bytes)})"
            )
        return InfoSectorPair.from_bytes_pair(primary_bytes, secondary_bytes).agreed

    def _read_map_sector(self, sin: SystemInternalName) -> MapSector:
        data = self._read_sector(int(sin))
        return MapSector.from_bytes(data, sin)

    def _read_map_chain(self, head_sin: SystemInternalName) -> MapChain:
        """Walk a map chain starting at ``head_sin``, returning the
        flattened :class:`MapChain` descriptor for the object.

        The walker reads every block in the chain eagerly via
        :meth:`_read_map_sector`. For typical objects (≤ 48 extents)
        this is a single disc read.
        """
        return MapChain.walk(head_sin, self._read_map_sector)

    def _read_object_bytes(self, sin: SystemInternalName) -> bytes:
        """Read the full byte contents of the object identified by ``sin``.

        Walks the object's map chain (which may be one or more blocks
        linked through their LSTENT slots), flattens the extents, and
        streams the result through :class:`ExtentStream`. See
        ``Uade13.asm:462-533`` (``MPGTSZ``) for the server's
        equivalent walk.
        """
        chain = self._read_map_chain(sin)
        stream = ExtentStream(chain, self._read_sector)
        return stream.read_all()

    def _read_directory(self, sin: SystemInternalName) -> AfsDirectory:
        raw = self._read_object_bytes(sin)
        return AfsDirectory.from_bytes(raw)

    def _resolve(
        self, path: AFSPath
    ) -> tuple[AfsDirectory, DirectoryEntry]:
        """Walk ``path`` from the root and return (parent_dir, entry).

        Raises :class:`AFSPathError` if any component is missing or
        if a non-final component is not a directory.
        """
        if path.is_root():
            raise AFSPathError("cannot resolve the root directory to a (parent, entry) pair")
        parts = path.parts[1:]  # skip the leading '$'
        current_dir = self._read_directory(self._info.root_sin)
        for depth, name in enumerate(parts):
            is_last = depth == len(parts) - 1
            try:
                entry = current_dir.find(name)
            except KeyError as exc:
                raise AFSPathError(
                    f"no entry named {name!r} under {'.'.join(path.parts[: depth + 1])}"
                ) from exc
            if is_last:
                return current_dir, entry
            if not entry.is_directory:
                raise AFSPathError(
                    f"component {name!r} of path {path} is a file, not a directory"
                )
            current_dir = self._read_directory(entry.sin)
        # Unreachable given the loop structure, but keeps the type
        # checker happy.
        raise AFSPathError(f"failed to resolve {path}")  # pragma: no cover

    def _resolve_directory(self, path: AFSPath) -> AfsDirectory:
        """Return the :class:`AfsDirectory` object that ``path`` names.

        Accepts the root path; otherwise requires the final component
        to be a directory.
        """
        if path.is_root():
            return self._read_directory(self._info.root_sin)
        _, entry = self._resolve(path)
        if not entry.is_directory:
            raise AFSPathError(f"{path} is a file, not a directory")
        return self._read_directory(entry.sin)

    # ------------------------------------------------------------------
    # Passwords file
    # ------------------------------------------------------------------

    def _load_passwords(self) -> PasswordsFile:
        try:
            passwords_path = self.root / PASSWORDS_FILENAME
            _, entry = self._resolve(passwords_path)
        except AFSPathError:
            # A disc without a passwords file is unusual but should
            # not make the whole handle unusable for file reads.
            # Surface an empty passwords file so callers see "no users".
            return PasswordsFile(())
        raw = self._read_object_bytes(entry.sin)
        return PasswordsFile.from_bytes(raw)

    # ------------------------------------------------------------------
    # Write primitives — phase 10+
    # ------------------------------------------------------------------

    def _write_sector(self, sector: int, data: bytes) -> None:
        """Buffer a 256-byte sector write at absolute address ``sector``.

        The write is held in memory until :meth:`flush` is called
        (either explicitly or by the context manager's ``__exit__``
        on a clean exit). On exception the buffer is discarded and
        the underlying disc is untouched.
        """
        if len(data) != MAP_SECTOR_SIZE:
            raise ValueError(
                f"sector write must be {MAP_SECTOR_SIZE} bytes, got {len(data)}"
            )
        if sector < 0 or sector >= self._disc.num_sectors:
            raise AFSError(
                f"sector {sector:#x} outside disc range 0..{self._disc.num_sectors - 1:#x}"
            )
        self._pending_writes[sector] = bytes(data)

    def _write_object_bytes(self, sin: SystemInternalName, data: bytes) -> None:
        """Write ``data`` to the object identified by ``sin``.

        The object's map chain must already cover at least
        ``len(data)`` bytes (rounded up to a sector). Use
        :meth:`_grow_object_by_sectors` first if you need to extend.
        The object is written sector by sector; the final sector may
        be partial in which case the tail is zero-padded.
        """
        chain = self._read_map_chain(sin)
        capacity_bytes = chain.total_sectors() * MAP_SECTOR_SIZE
        if len(data) > capacity_bytes:
            raise AFSError(
                f"object {int(sin):#x} has capacity {capacity_bytes} bytes; "
                f"cannot write {len(data)} bytes"
            )
        # Walk extents writing data sectors; tail-pad the last sector
        # with zeros if data isn't a whole-sector multiple.
        cursor = 0
        for extent in chain.flat_extents():
            for offset in range(extent.length):
                if cursor >= len(data):
                    return
                sector_addr = int(extent.start) + offset
                chunk = data[cursor : cursor + MAP_SECTOR_SIZE]
                if len(chunk) < MAP_SECTOR_SIZE:
                    chunk = chunk + b"\x00" * (MAP_SECTOR_SIZE - len(chunk))
                self._write_sector(sector_addr, chunk)
                cursor += MAP_SECTOR_SIZE

    # ------------------------------------------------------------------
    # Bitmap shadow + allocator (lazy, cached per session)
    # ------------------------------------------------------------------

    def _bitmap_shadow(self):
        """Return the session's :class:`BitmapShadow`, creating on first use.

        Cylinder indices are 0-based relative to the start of the
        region. The reader and writer translate to absolute-disc
        sectors via ``(start_cylinder + index) * sectors_per_cylinder``.
        """
        if self._bitmap_shadow_cache is not None:
            return self._bitmap_shadow_cache

        from oaknut.afs.bitmap import BitmapShadow

        spc = self._info.sectors_per_cylinder
        start_cyl = self._info.start_cylinder
        num_cylinders = self._info.cylinders - start_cyl

        def reader(cyl_index: int) -> bytes:
            physical = start_cyl + cyl_index
            return self._read_sector(physical * spc)

        def writer(cyl_index: int, data: bytes) -> None:
            physical = start_cyl + cyl_index
            self._write_sector(physical * spc, data)

        self._bitmap_shadow_cache = BitmapShadow(
            num_cylinders=num_cylinders,
            sectors_per_cylinder=spc,
            reader=reader,
            writer=writer,
        )
        return self._bitmap_shadow_cache

    def _allocator(self):
        """Return the session's :class:`Allocator`, creating on first use."""
        if self._allocator_cache is not None:
            return self._allocator_cache

        from oaknut.afs.allocator import Allocator

        self._allocator_cache = Allocator(
            self._bitmap_shadow(),
            start_cylinder=self._info.start_cylinder,
            sectors_per_cylinder=self._info.sectors_per_cylinder,
        )
        return self._allocator_cache

    # ------------------------------------------------------------------
    # Object growth — phase 10
    # ------------------------------------------------------------------

    def _grow_object_by_sectors(
        self,
        sin: SystemInternalName,
        additional_sectors: int,
    ) -> int:
        """Extend an object's map chain by ``additional_sectors`` sectors.

        Allocates fresh data sectors and appends them as extents to
        the last map block in the chain. If the last block would
        overflow 48 data extents, a new successor map block is
        allocated and chained from slot 48, matching
        ``MAPMAN.CHANGESIZE`` (``Uade10:355`` ``MPCHSZ``) and
        ``MKRLN`` (``Uade12:187``).

        Returns the new total size in sectors.
        """
        if additional_sectors <= 0:
            raise ValueError(f"additional_sectors must be positive, got {additional_sectors}")

        allocator = self._allocator()
        new_extents = allocator.allocate(additional_sectors)

        chain = self._read_map_chain(sin)
        last_block = chain.last

        merged = list(last_block.extents)
        for extent in new_extents:
            if merged and int(merged[-1].end) == int(extent.start):
                prev = merged[-1]
                merged[-1] = Extent(start=prev.start, length=prev.length + extent.length)
            else:
                merged.append(extent)

        if len(merged) <= _MAX_DATA_EXTENTS:
            new_last = MapSector(
                sin=last_block.sin,
                extents=tuple(merged),
                last_sector_bytes=0,
                sequence_number=(last_block.sequence_number + 1) & 0xFF,
                next_sin=last_block.next_sin,
            )
            self._write_sector(int(last_block.sin), new_last.to_bytes())
        else:
            # Overflow: keep the first 48 in the current block and
            # spill the rest into a freshly-allocated successor.
            keep = merged[:_MAX_DATA_EXTENTS]
            spill = merged[_MAX_DATA_EXTENTS:]
            successor_sin = allocator.allocate_sector()
            updated_last = MapSector(
                sin=last_block.sin,
                extents=tuple(keep),
                last_sector_bytes=0,
                sequence_number=(last_block.sequence_number + 1) & 0xFF,
                next_sin=successor_sin,
            )
            self._write_sector(int(last_block.sin), updated_last.to_bytes())
            successor = MapSector(
                sin=successor_sin,
                extents=tuple(spill),
                last_sector_bytes=0,
                sequence_number=0,
                next_sin=None,
            )
            self._write_sector(int(successor_sin), successor.to_bytes())

        self._bitmap_shadow().flush()
        return chain.total_sectors() + additional_sectors

    # ------------------------------------------------------------------
    # Object creation / destruction — phase 11+
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Quota enforcement — follow-up 5
    # ------------------------------------------------------------------

    def _debit_quota(self, num_sectors: int) -> None:
        """Debit ``num_sectors`` worth of space from the acting user's quota.

        Raises :class:`AFSQuotaExceededError` if the user's remaining
        free space would go negative. No-op when ``enforce_quota`` is
        False (for tests and system-level operations).
        """
        from oaknut.afs.exceptions import AFSQuotaExceededError

        if not self._enforce_quota:
            return
        try:
            user_record = self.users.find(self._acting_user)
        except KeyError:
            return
        cost = num_sectors * MAP_SECTOR_SIZE
        if user_record.free_space < cost:
            raise AFSQuotaExceededError(
                f"user {self._acting_user!r} has {user_record.free_space} bytes free "
                f"but {cost} bytes are needed"
            )
        new_passwords = self.users.with_quota(self._acting_user, user_record.free_space - cost)
        self._update_passwords_on_disc(new_passwords)

    def _credit_quota(self, num_sectors: int) -> None:
        """Credit ``num_sectors`` worth of space back to the acting user."""
        if not self._enforce_quota:
            return
        try:
            user_record = self.users.find(self._acting_user)
        except KeyError:
            return
        credit = num_sectors * MAP_SECTOR_SIZE
        new_free = min(user_record.free_space + credit, 0xFFFFFFFF)
        new_passwords = self.users.with_quota(self._acting_user, new_free)
        self._update_passwords_on_disc(new_passwords)

    def _update_passwords_on_disc(self, new_passwords: PasswordsFile) -> None:
        """Serialise ``new_passwords`` and write through the passwords file's
        existing map chain, replacing the cached parse.
        """
        passwords_path = self.root / PASSWORDS_FILENAME
        try:
            _, entry = self._resolve(passwords_path)
        except AFSPathError:
            return
        raw = new_passwords.to_bytes()
        if len(raw) < MAP_SECTOR_SIZE:
            raw = raw.ljust(MAP_SECTOR_SIZE, b"\x00")
        self._write_object_bytes(entry.sin, raw)
        self._passwords_cache = new_passwords

    @staticmethod
    def _coalesce_extents(extents: list[Extent]) -> list[Extent]:
        """Merge physically-adjacent extents into longer runs."""
        coalesced: list[Extent] = []
        for extent in extents:
            if coalesced and int(coalesced[-1].end) == int(extent.start):
                prev = coalesced[-1]
                coalesced[-1] = Extent(
                    start=prev.start,
                    length=prev.length + extent.length,
                )
            else:
                coalesced.append(extent)
        return coalesced

    def _create_object(
        self,
        data: bytes,
    ) -> SystemInternalName:
        """Allocate a new file or directory object from ``data`` bytes.

        Mirrors ``MPCRSP`` (``Uade10.asm:84-255``): allocate data
        sectors, allocate one map block SIN per 48-extent chunk,
        build the chain with slot-48 pointers between blocks, write
        everything to disc, return the head block's SIN.

        Handles arbitrarily large objects by chaining multiple map
        blocks when the coalesced extent count exceeds 48. Debits
        the acting user's quota when enforcement is on.
        """
        allocator = self._allocator()

        n_data_sectors = (len(data) + MAP_SECTOR_SIZE - 1) // MAP_SECTOR_SIZE

        # Quota check before touching the allocator.
        n_map_blocks = max(1, (n_data_sectors + _MAX_DATA_EXTENTS - 1) // _MAX_DATA_EXTENTS)
        total_sectors_needed = n_data_sectors + n_map_blocks
        self._debit_quota(total_sectors_needed)
        data_extents: list[Extent] = []
        if n_data_sectors > 0:
            data_extents = allocator.allocate(n_data_sectors)

        coalesced = self._coalesce_extents(data_extents)

        # Split into 48-extent chunks, one per map block.
        n_blocks = max(1, (len(coalesced) + _MAX_DATA_EXTENTS - 1) // _MAX_DATA_EXTENTS)
        chunks: list[tuple[Extent, ...]] = []
        for i in range(n_blocks):
            start = i * _MAX_DATA_EXTENTS
            end = min(start + _MAX_DATA_EXTENTS, len(coalesced))
            chunks.append(tuple(coalesced[start:end]))

        # Allocate one SIN per map block.
        block_sins: list[SystemInternalName] = []
        try:
            for _ in range(n_blocks):
                block_sins.append(allocator.allocate_sector())
        except Exception:
            for sin in block_sins:
                allocator.free_sector(sin)
            if data_extents:
                allocator.free_extents(data_extents)
            raise

        last_sector_bytes = len(data) % MAP_SECTOR_SIZE

        # Build and write each map block.
        for i, (sin, chunk) in enumerate(zip(block_sins, chunks)):
            is_last = i == n_blocks - 1
            next_sin = None if is_last else block_sins[i + 1]
            block = MapSector(
                sin=sin,
                extents=chunk,
                last_sector_bytes=last_sector_bytes if is_last else 0,
                sequence_number=0,
                next_sin=next_sin,
            )
            self._write_sector(int(sin), block.to_bytes())

        # Write data sectors (tail-padded if needed).
        cursor = 0
        for extent in coalesced:
            for offset in range(extent.length):
                chunk_data = data[cursor : cursor + MAP_SECTOR_SIZE]
                if len(chunk_data) < MAP_SECTOR_SIZE:
                    chunk_data = chunk_data + b"\x00" * (MAP_SECTOR_SIZE - len(chunk_data))
                self._write_sector(int(extent.start) + offset, chunk_data)
                cursor += MAP_SECTOR_SIZE

        self._bitmap_shadow().flush()
        return block_sins[0]

    def _delete_object(self, sin: SystemInternalName) -> None:
        """Free every sector belonging to the object at ``sin``.

        Walks the map chain, releases each data extent back to the
        allocator, then releases every map block in the chain.
        Credits the acting user's quota when enforcement is on.
        """
        allocator = self._allocator()
        chain = self._read_map_chain(sin)
        total_freed = chain.total_sectors() + len(chain.blocks)
        for block in chain.blocks:
            for extent in block.extents:
                allocator.free_extent(extent)
            allocator.free_sector(int(block.sin))
        self._bitmap_shadow().flush()
        self._credit_quota(total_freed)

    # ------------------------------------------------------------------
    # High-level file write — phase 11
    # ------------------------------------------------------------------

    def _write_file(
        self,
        parent_dir_sin: SystemInternalName,
        name: str,
        data: bytes,
        *,
        load_address: int,
        exec_address: int,
        access,
        date,
    ) -> SystemInternalName:
        """Create a new file object and link it into ``parent_dir_sin``.

        If an entry with ``name`` already exists in the parent, its
        old object is freed first and the directory entry is rewritten
        to point at the new one — matching the RETANB replace path at
        ``Uade0E.asm:806`` semantically (though the ROM's version
        preserves access byte; we honour the caller's).
        """
        from oaknut.afs.directory import DirectoryEntry as _DirectoryEntry
        from oaknut.afs.directory import delete_entry as _delete_entry_bytes

        parent_raw = self._read_object_bytes(parent_dir_sin)
        parent_dir = AfsDirectory.from_bytes(parent_raw)
        if parent_dir.contains(name):
            existing = parent_dir[name]
            self._delete_object(existing.sin)
            updated_parent = _delete_entry_bytes(parent_raw, name)
            self._write_object_bytes(parent_dir_sin, updated_parent)

        new_sin = self._create_object(data)

        entry = _DirectoryEntry(
            name=name,
            load_address=load_address,
            exec_address=exec_address,
            access=access,
            date=date,
            sin=new_sin,
        )
        self.insert_into_directory(parent_dir_sin, entry)
        return new_sin

    def _resolve_parent_and_name(
        self,
        path: AFSPath,
    ) -> tuple[SystemInternalName, str]:
        """Return ``(parent_dir_sin, final_name)`` for a non-root path.

        Raises :class:`AFSPathError` if ``path`` is the root, or if
        the parent cannot be resolved.
        """
        if path.is_root():
            raise AFSPathError("cannot operate on the root directory this way")
        if len(path.parts) == 2:
            # Child of root.
            return SystemInternalName(int(self._info.root_sin)), path.parts[1]
        parent_path = path.parent
        _, parent_entry = self._resolve(parent_path)
        if not parent_entry.is_directory:
            raise AFSPathError(f"parent {parent_path} is a file, not a directory")
        return SystemInternalName(int(parent_entry.sin)), path.parts[-1]

    # ------------------------------------------------------------------
    # Directory insert with auto-grow — phase 10
    # ------------------------------------------------------------------

    def insert_into_directory(
        self,
        dir_sin: SystemInternalName,
        entry: DirectoryEntry,
    ) -> None:
        """Insert ``entry`` into the directory at ``dir_sin``.

        Reads the directory bytes, calls
        :func:`~oaknut.afs.directory.insert_entry`, and writes the
        result back. If the directory's free list is empty the
        underlying object is grown by one disc block (matching
        ``CHZSZE`` at ``Uade0E:1167``) and the insert is retried.
        The grow step is capped at ``MAXDIR = 26`` sectors.

        Raises :class:`AFSDirectoryFullError` if the directory is
        already at ``MAXDIR`` and a grow would exceed the cap.
        """
        raw = self._read_object_bytes(dir_sin)
        try:
            new_raw = insert_entry(raw, entry)
        except AFSDirectoryFullError:
            new_size = len(raw) + _DIRECTORY_GROW_STEP_BYTES
            if new_size > _MAX_DIRECTORY_BYTES:
                raise AFSDirectoryFullError(
                    f"directory at sin {int(dir_sin):#x} already at MAXDIR "
                    f"({_MAX_DIRECTORY_BYTES} bytes); cannot grow further"
                ) from None
            # Grow the underlying object first, then reformat the
            # in-memory bytes, then re-run the insert.
            self._grow_object_by_sectors(dir_sin, _DIRECTORY_GROW_STEP_BYTES // MAP_SECTOR_SIZE)
            grown_raw = grow_directory_bytes(raw, new_size)
            new_raw = insert_entry(grown_raw, entry)

        self._write_object_bytes(dir_sin, new_raw)

    # ------------------------------------------------------------------
    # Context manager interface
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """Commit all buffered sector writes to the underlying disc.

        The bitmap shadow is flushed first (which adds any dirty
        bitmap sectors to ``_pending_writes`` via the shadow's writer
        callback), then every entry in the buffer is written to the
        ``UnifiedDisc`` in a single pass. After a successful flush
        the buffer is empty.
        """
        if self._bitmap_shadow_cache is not None:
            self._bitmap_shadow_cache.flush()
        for sector, data in sorted(self._pending_writes.items()):
            view = self._disc.sector_range(sector, 1)
            view[:] = data
        self._pending_writes.clear()

    def discard(self) -> None:
        """Drop all buffered writes without touching the disc.

        Called on exception exit. Also invalidates the bitmap shadow
        and allocator caches so they don't carry stale state from
        the discarded session.
        """
        self._pending_writes.clear()
        self._bitmap_shadow_cache = None
        self._allocator_cache = None
        self._passwords_cache = None

    def __enter__(self) -> AFS:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.flush()
        else:
            self.discard()

    def __repr__(self) -> str:
        return (
            f"AFS(disc_name={self.disc_name!r}, "
            f"start_cylinder={self.start_cylinder}, "
            f"sec1={self._sec1:#x}, sec2={self._sec2:#x})"
        )

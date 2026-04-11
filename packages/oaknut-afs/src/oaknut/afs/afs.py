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

from oaknut.afs.directory import AfsDirectory, DirectoryEntry
from oaknut.afs.exceptions import (
    AFSError,
    AFSInfoSectorError,
    AFSPathError,
)
from oaknut.afs.info_sector import INFO_SECTOR_SIZE, InfoSector, InfoSectorPair
from oaknut.afs.map_sector import MAP_SECTOR_SIZE, ExtentStream, MapSector
from oaknut.afs.passwords import PASSWORDS_FILENAME, PasswordsFile
from oaknut.afs.path import AFSPath
from oaknut.afs.types import Geometry, SystemInternalName

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
    ) -> None:
        if sec1 <= 0 or sec2 <= 0:
            raise AFSNotPresentError(
                f"AFS info-sector pointers are zero (sec1={sec1}, sec2={sec2}); "
                "disc has no AFS partition"
            )
        self._disc = unified_disc
        self._sec1 = sec1
        self._sec2 = sec2
        self._info: InfoSector = self._read_and_verify_info()
        # Lazy cache of the passwords file parse; None until first access.
        self._passwords_cache: PasswordsFile | None = None

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
        """Total free data sectors across all cylinders in the region.

        Summed by reading every cylinder's bitmap sector. Phase 8's
        :class:`BitmapShadow` will cache this; phase 6 recomputes on
        each access because the answer is only used for display.
        """

        shadow = self._build_bitmap_shadow()
        total = 0
        for cyl in range(shadow.num_cylinders):
            total += shadow.bitmap_for(cyl).free_count()
        return total

    # ------------------------------------------------------------------
    # Read primitives
    # ------------------------------------------------------------------

    def _read_sector(self, sector: int) -> bytes:
        """Read one 256-byte sector by absolute address."""
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

    def _read_object_bytes(self, sin: SystemInternalName) -> bytes:
        """Read the full byte contents of the object identified by ``sin``.

        Resolves the object's map sector and streams its extents
        through :class:`ExtentStream`. Handles single-map-sector
        objects only; chained maps arrive in phase 7.
        """
        map_sector = self._read_map_sector(sin)
        stream = ExtentStream(map_sector, self._read_sector)
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
    # Bitmap plumbing for free_sectors
    # ------------------------------------------------------------------

    def _build_bitmap_shadow(self):
        """Construct a :class:`BitmapShadow` for this AFS region.

        Cylinder indices are 0-based relative to the start of the
        region (as the shadow expects). The reader translates those
        to absolute-disc sectors via
        ``(start_cylinder + index) * sectors_per_cylinder``.
        """
        from oaknut.afs.bitmap import BitmapShadow

        spc = self._info.sectors_per_cylinder
        start_cyl = self._info.start_cylinder
        num_cylinders = self._info.cylinders - start_cyl

        def reader(cyl_index: int) -> bytes:
            physical = start_cyl + cyl_index
            return self._read_sector(physical * spc)

        def writer(cyl_index: int, data: bytes) -> None:
            # Read path only for phase 6; the bitmap shadow will
            # only invoke this from mutations, which we don't do.
            raise AFSError("AFS is read-only in phase 6; cannot write bitmap")

        return BitmapShadow(
            num_cylinders=num_cylinders,
            sectors_per_cylinder=spc,
            reader=reader,
            writer=writer,
        )

    # ------------------------------------------------------------------
    # Context manager interface (read-only in phase 6)
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """Flush pending mutations. No-op in phase 6 (read-only)."""

    def __enter__(self) -> AFS:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.flush()

    def __repr__(self) -> str:
        return (
            f"AFS(disc_name={self.disc_name!r}, "
            f"start_cylinder={self.start_cylinder}, "
            f"sec1={self._sec1:#x}, sec2={self._sec2:#x})"
        )

"""ADFS filesystem operations — public API.

Provides ADFS (the filesystem handle), ADFSPath (pathlib-inspired navigation),
and ADFSStat (file/directory metadata).

Example usage:

    with ADFS.from_file("games.adf") as adfs:
        for entry in adfs.root:
            print(f"{entry.name:10s} {entry.stat().length:6d}")

        data = (adfs.root / "Games" / "Elite").read_bytes()
"""

from __future__ import annotations

import mmap
from contextlib import contextmanager
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Iterator, Union

from oaknut_dfs.adfs_directory import (
    ADFSDirectoryFormat,
    OldDirectoryFormat,
    _ADFSDirectory,
    _ADFSDirectoryEntry,
)
from oaknut_dfs.adfs_free_space_map import OldFreeSpaceMap
from oaknut_dfs.exceptions import ADFSError, ADFSPathError
from oaknut_dfs.surface import DiscImage, SurfaceSpec
from oaknut_dfs.unified_disc import UnifiedDisc


_ADFS_SECTORS_PER_TRACK = 16
_ADFS_BYTES_PER_SECTOR = 256

# Root directory sector address for old map formats
_OLD_MAP_ROOT_SECTOR = 2
_OLD_DIR_SECTORS = 5  # Old directory occupies 5 sectors
_OLD_FSM_SECTORS = 2  # Old free space map occupies sectors 0-1


# --- ADFS format constants ---


@dataclass(frozen=True)
class ADFSFormat:
    """ADFS disc format specification."""

    surface_specs: list[SurfaceSpec]
    total_sectors: int
    total_bytes: int
    label: str

    def __post_init__(self):
        if not self.surface_specs:
            raise ValueError("At least one surface_spec is required")


def _single_sided_spec(num_tracks: int) -> SurfaceSpec:
    track_size = _ADFS_SECTORS_PER_TRACK * _ADFS_BYTES_PER_SECTOR
    return SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=_ADFS_SECTORS_PER_TRACK,
        bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
        track_zero_offset_bytes=0,
        track_stride_bytes=track_size,
    )


def _interleaved_double_sided_specs(num_tracks: int) -> list[SurfaceSpec]:
    track_size = _ADFS_SECTORS_PER_TRACK * _ADFS_BYTES_PER_SECTOR
    return [
        SurfaceSpec(
            num_tracks=num_tracks,
            sectors_per_track=_ADFS_SECTORS_PER_TRACK,
            bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
            track_zero_offset_bytes=0,
            track_stride_bytes=2 * track_size,
        ),
        SurfaceSpec(
            num_tracks=num_tracks,
            sectors_per_track=_ADFS_SECTORS_PER_TRACK,
            bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
            track_zero_offset_bytes=track_size,
            track_stride_bytes=2 * track_size,
        ),
    ]


ADFS_S = ADFSFormat(
    surface_specs=[_single_sided_spec(40)],
    total_sectors=640,
    total_bytes=163840,
    label="S",
)

ADFS_M = ADFSFormat(
    surface_specs=[_single_sided_spec(80)],
    total_sectors=1280,
    total_bytes=327680,
    label="M",
)

ADFS_L = ADFSFormat(
    surface_specs=_interleaved_double_sided_specs(80),
    total_sectors=2560,
    total_bytes=655360,
    label="L",
)

_ADFS_FORMATS_BY_SIZE = {
    ADFS_S.total_bytes: ADFS_S,
    ADFS_M.total_bytes: ADFS_M,
    ADFS_L.total_bytes: ADFS_L,
}


# --- Hard disc (.dat/.dsc) support ---

_DSC_SIZE = 22
_SCSI_SECTORS_PER_TRACK = 33


@dataclass(frozen=True)
class _DSCGeometry:
    """Disc geometry from a SCSI .dsc sidecar file."""

    cylinders: int
    heads: int
    sectors_per_track: int = _SCSI_SECTORS_PER_TRACK


def _parse_dsc(filepath: Union[str, PathLike]) -> _DSCGeometry:
    """Parse a 22-byte .dsc sidecar file.

    The .dsc file contains SCSI MODE SENSE data with disc geometry:
      Bytes 13–14: cylinders (big-endian 16-bit)
      Byte 15: number of heads
      Sectors per track is always 33.
    """
    data = Path(filepath).read_bytes()
    if len(data) != _DSC_SIZE:
        raise ADFSError(
            f"DSC file should be {_DSC_SIZE} bytes, got {len(data)}"
        )
    return _DSCGeometry(
        cylinders=(data[13] << 8) | data[14],
        heads=data[15],
    )


def _hard_disc_format(
    geometry: _DSCGeometry, dat_size_bytes: int
) -> ADFSFormat:
    """Create an ADFSFormat for a hard disc image from geometry and file size.

    ADFS addresses hard discs using linear SCSI LBA — sector N is at
    byte offset N×256 in the .dat file.  The CHS geometry from the .dsc
    file describes the physical drive but is not used for ADFS sector
    addressing.  We model the image as a single flat surface matching
    ADFS's linear view.  The geometry is recorded in the format for
    metadata but doesn't affect addressing.
    """
    if dat_size_bytes % _ADFS_BYTES_PER_SECTOR != 0:
        raise ADFSError(
            f"Hard disc image size ({dat_size_bytes}) is not a multiple "
            f"of the sector size ({_ADFS_BYTES_PER_SECTOR})"
        )

    total_sectors = dat_size_bytes // _ADFS_BYTES_PER_SECTOR

    # Model as cylinders of (heads × sectors_per_track) sectors each,
    # laid out sequentially — a single surface with the full linear
    # sector space.
    sectors_per_cylinder = geometry.heads * geometry.sectors_per_track
    num_cylinders = total_sectors // sectors_per_cylinder
    if num_cylinders == 0:
        num_cylinders = 1
        sectors_per_cylinder = total_sectors

    spec = SurfaceSpec(
        num_tracks=num_cylinders,
        sectors_per_track=sectors_per_cylinder,
        bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
        track_zero_offset_bytes=0,
        track_stride_bytes=sectors_per_cylinder * _ADFS_BYTES_PER_SECTOR,
    )

    return ADFSFormat(
        surface_specs=[spec],
        total_sectors=total_sectors,
        total_bytes=dat_size_bytes,
        label="HardDisc",
    )


# --- Public value type ---


@dataclass(frozen=True)
class ADFSStat:
    """File/directory metadata, analogous to os.stat_result."""

    length: int
    load_address: int
    exec_address: int
    locked: bool
    owner_read: bool
    owner_write: bool
    owner_execute: bool
    public_read: bool
    public_write: bool
    public_execute: bool
    is_directory: bool


def _entry_to_stat(entry: _ADFSDirectoryEntry) -> ADFSStat:
    """Convert an internal directory entry to a public ADFSStat."""
    return ADFSStat(
        length=entry.length,
        load_address=entry.load_address,
        exec_address=entry.exec_address,
        locked=entry.attributes.locked,
        owner_read=entry.attributes.owner_read,
        owner_write=entry.attributes.owner_write,
        owner_execute=entry.attributes.owner_execute,
        public_read=entry.attributes.public_read,
        public_write=entry.attributes.public_write,
        public_execute=entry.attributes.public_execute,
        is_directory=entry.attributes.directory,
    )


# --- ADFSPath ---


class ADFSPath:
    """A path within an ADFS filesystem, inspired by pathlib.Path.

    ADFSPath objects are lightweight handles that reference an ADFS
    filesystem and a normalised absolute path string. They do not
    cache directory contents, so they always reflect the current
    state of the disc image.

    Navigation uses the ``/`` operator::

        games = adfs.root / "Games"
        elite = games / "Elite"

    Iterate over directory contents::

        for child in games:
            print(child.name)

    Read file data::

        data = elite.read_bytes()
    """

    def __init__(self, adfs: ADFS, path: str):
        self._adfs = adfs
        self._path = path

    # --- Navigation ---

    def __truediv__(self, name: str) -> ADFSPath:
        """Join path components: ``root / "Games" / "Elite"``."""
        if self._path == "$":
            return ADFSPath(self._adfs, f"$.{name}")
        return ADFSPath(self._adfs, f"{self._path}.{name}")

    @property
    def parent(self) -> ADFSPath:
        """Parent directory."""
        parts = self._path.split(".")
        if len(parts) <= 1:
            return self  # Root's parent is itself
        return ADFSPath(self._adfs, ".".join(parts[:-1]))

    @property
    def name(self) -> str:
        """Final component of the path."""
        return self._path.split(".")[-1]

    @property
    def parts(self) -> tuple[str, ...]:
        """Path components as a tuple, e.g. ``("$", "Games", "Elite")``."""
        return tuple(self._path.split("."))

    @property
    def path(self) -> str:
        """Full path string, e.g. ``"$.Games.Elite"``."""
        return self._path

    # --- Querying ---

    def exists(self) -> bool:
        """Check whether this path exists on disc."""
        if self._path == "$":
            return True
        try:
            self._resolve()
            return True
        except ADFSPathError:
            return False

    def is_dir(self) -> bool:
        """Check whether this path is a directory."""
        if self._path == "$":
            return True
        try:
            _, entry = self._resolve()
            return entry.is_directory
        except ADFSPathError:
            return False

    def is_file(self) -> bool:
        """Check whether this path is a file (not a directory)."""
        if self._path == "$":
            return False
        try:
            _, entry = self._resolve()
            return not entry.is_directory
        except ADFSPathError:
            return False

    def stat(self) -> ADFSStat:
        """Return metadata for this path.

        Raises:
            ADFSPathError: If the path does not exist.
        """
        if self._path == "$":
            return ADFSStat(
                length=self._adfs._dir_format.size_in_bytes,
                load_address=0,
                exec_address=0,
                locked=False,
                owner_read=True,
                owner_write=True,
                owner_execute=False,
                public_read=True,
                public_write=False,
                public_execute=False,
                is_directory=True,
            )
        _, entry = self._resolve()
        return _entry_to_stat(entry)

    # --- Directory operations ---

    def iterdir(self) -> Iterator[ADFSPath]:
        """Iterate over directory contents.

        Raises:
            ADFSPathError: If this path is not a directory or doesn't exist.
        """
        directory = self._resolve_as_directory()
        for entry in directory.entries:
            yield self / entry.name

    def walk(self) -> Iterator[tuple[ADFSPath, list[str], list[str]]]:
        """Walk directory tree, like ``os.walk()``.

        Yields ``(dirpath, dirnames, filenames)`` tuples.
        """
        directory = self._resolve_as_directory()
        dirnames = [e.name for e in directory.entries if e.is_directory]
        filenames = [e.name for e in directory.entries if not e.is_directory]
        yield self, dirnames, filenames

        for dirname in dirnames:
            yield from (self / dirname).walk()

    # --- File operations ---

    def read_bytes(self) -> bytes:
        """Read file contents.

        Raises:
            ADFSPathError: If the path doesn't exist or is a directory.
        """
        if self._path == "$":
            raise ADFSPathError("Cannot read root directory as file")
        _, entry = self._resolve()
        if entry.is_directory:
            raise ADFSPathError(f"'{self._path}' is a directory, not a file")
        return self._adfs._read_file_data(entry)

    # --- Export ---

    def export(self, target_filepath: Union[str, PathLike], *,
               preserve_metadata: bool = True) -> None:
        """Export file to host filesystem, optionally with .inf metadata.

        Args:
            target_filepath: Destination path on the host filesystem.
            preserve_metadata: If True, write a .inf sidecar file with
                load/exec addresses and attributes.
        """
        import pathlib

        target = pathlib.Path(target_filepath)
        data = self.read_bytes()
        target.write_bytes(data)

        if preserve_metadata:
            _, entry = self._resolve()
            inf_filepath = target.with_suffix(target.suffix + ".inf")
            locked_str = "L" if entry.attributes.locked else ""
            inf_filepath.write_text(
                f"{self.name} {entry.load_address:08X} "
                f"{entry.exec_address:08X} {entry.length:08X} {locked_str}\n"
            )

    # --- Protocols ---

    def __str__(self) -> str:
        return self._path

    def __repr__(self) -> str:
        return f"ADFSPath({self._path!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ADFSPath):
            return NotImplemented
        return self._adfs is other._adfs and self._path.upper() == other._path.upper()

    def __hash__(self) -> int:
        return hash(self._path.upper())

    def __iter__(self) -> Iterator[ADFSPath]:
        """Shorthand for ``iterdir()``."""
        return self.iterdir()

    def __contains__(self, name: str) -> bool:
        """Check if *name* exists in this directory."""
        directory = self._resolve_as_directory()
        return directory.find(name) is not None

    # --- Internal helpers ---

    def _resolve(self) -> tuple[_ADFSDirectory, _ADFSDirectoryEntry]:
        """Navigate the directory tree to find this path's entry.

        Returns:
            (parent_directory, entry) tuple.

        Raises:
            ADFSPathError: If the path doesn't exist.
        """
        parts = self._path.split(".")
        if not parts or parts[0] != "$":
            raise ADFSPathError(f"Path must start with '$': {self._path!r}")

        if len(parts) == 1:
            raise ADFSPathError("Cannot resolve root directory as an entry")

        current_dir = self._adfs._read_root_directory()

        for i, component in enumerate(parts[1:], 1):
            entry = current_dir.find(component)
            if entry is None:
                partial = ".".join(parts[:i + 1])
                raise ADFSPathError(f"'{component}' not found in '{partial}'")

            if i < len(parts) - 1:
                # Need to descend into this directory
                if not entry.is_directory:
                    partial = ".".join(parts[:i + 1])
                    raise ADFSPathError(f"'{partial}' is not a directory")
                current_dir = self._adfs._read_directory_at(
                    entry.indirect_disc_address
                )

        return current_dir, entry

    def _resolve_as_directory(self) -> _ADFSDirectory:
        """Resolve this path as a directory.

        Raises:
            ADFSPathError: If the path is not a directory.
        """
        if self._path == "$":
            return self._adfs._read_root_directory()

        parent_dir, entry = self._resolve()
        if not entry.is_directory:
            raise ADFSPathError(f"'{self._path}' is not a directory")
        return self._adfs._read_directory_at(entry.indirect_disc_address)


# --- ADFS filesystem handle ---


def _detect_format(buffer_size: int) -> ADFSFormat:
    """Detect ADFS format from image file size.

    Raises:
        ADFSError: If the size doesn't match any known ADFS floppy format.
    """
    fmt = _ADFS_FORMATS_BY_SIZE.get(buffer_size)
    if fmt is None:
        sizes = ", ".join(
            f"{f.total_bytes} ({f.label})" for f in _ADFS_FORMATS_BY_SIZE.values()
        )
        raise ADFSError(
            f"Unrecognised ADFS image size: {buffer_size} bytes. Expected {sizes}."
        )
    return fmt


def _initialise_old_free_space_map(
    unified: UnifiedDisc,
    total_sectors: int,
    boot_option: int = 0,
) -> None:
    """Write an empty old-format free space map to sectors 0–1."""
    from oaknut_dfs.adfs_free_space_map import _calculate_old_map_checksum

    data = unified.sector_range(0, 2)

    # Single free space entry: everything after the root directory
    used_sectors = _OLD_FSM_SECTORS + _OLD_DIR_SECTORS  # 7
    free_start = used_sectors
    free_length = total_sectors - used_sectors

    # FreeStart[0] at 0x000 (3 bytes LE)
    data[0x000] = free_start & 0xFF
    data[0x001] = (free_start >> 8) & 0xFF
    data[0x002] = (free_start >> 16) & 0xFF

    # FreeLen[0] at 0x100 (3 bytes LE)
    data[0x100] = free_length & 0xFF
    data[0x101] = (free_length >> 8) & 0xFF
    data[0x102] = (free_length >> 16) & 0xFF

    # OldSize at 0x0FC (3 bytes LE)
    data[0x0FC] = total_sectors & 0xFF
    data[0x0FD] = (total_sectors >> 8) & 0xFF
    data[0x0FE] = (total_sectors >> 16) & 0xFF

    # Boot option at 0x1FD
    data[0x1FD] = boot_option

    # FreeEnd pointer at 0x1FE (1 entry × 3 bytes)
    data[0x1FE] = 3

    # Calculate and write checksums
    data[0x0FF] = _calculate_old_map_checksum(data, 0x000)
    data[0x1FF] = _calculate_old_map_checksum(data, 0x100)


def _initialise_old_root_directory(
    unified: UnifiedDisc,
    title: str = "",
) -> None:
    """Write an empty old-format root directory to sectors 2–6."""
    data = unified.sector_range(_OLD_MAP_ROOT_SECTOR, _OLD_DIR_SECTORS)

    # Header
    data[0x00] = 0  # StartMasSeq
    data[0x01:0x05] = b"Hugo"  # StartName

    # Entries area: all zeros (empty) — already zero from buffer init

    # Tail at offset 0x4CB
    tail = 0x4CB
    data[tail] = 0x00  # OldDirLastMark

    # Directory name: "$" + null padding
    data[tail + 1] = ord("$")
    # Bytes tail+2 through tail+10 are zero (already)

    # Parent address: root's parent is itself (sector 2 = 0x000002)
    data[tail + 11] = _OLD_MAP_ROOT_SECTOR & 0xFF
    data[tail + 12] = (_OLD_MAP_ROOT_SECTOR >> 8) & 0xFF
    data[tail + 13] = (_OLD_MAP_ROOT_SECTOR >> 16) & 0xFF

    # Title (19 bytes, null-terminated)
    title_bytes = title.encode("ascii")[:19]
    for i, b in enumerate(title_bytes):
        data[tail + 14 + i] = b

    # Reserved (14 bytes): already zero

    # EndMasSeq
    data[tail + 47] = 0  # Must match StartMasSeq
    # EndName
    data[tail + 48:tail + 52] = b"Hugo"
    # DirCheckByte: reserved, must be zero
    data[tail + 52] = 0x00


class ADFS:
    """Handle to an open ADFS disc image.

    The ADFS object provides disc-level metadata and serves as the factory
    for ADFSPath objects. File and directory operations are performed through
    ADFSPath.

    Example::

        with ADFS.from_file("games.adf") as adfs:
            games = adfs.root / "Games"
            for entry in games:
                print(entry.name, entry.stat().length)
            data = (games / "Elite").read_bytes()
    """

    def __init__(
        self,
        unified_disc: UnifiedDisc,
        dir_format: ADFSDirectoryFormat,
        fsm: OldFreeSpaceMap,
    ):
        self._disc = unified_disc
        self._dir_format = dir_format
        self._fsm = fsm

    # --- Named constructors ---

    @staticmethod
    @contextmanager
    def from_file(
        filepath: Union[str, PathLike],
        *,
        mode: str = "rb",
    ) -> Iterator[ADFS]:
        """Open an ADFS disc image file as a context manager.

        For floppy images (``.adf``, ``.adl``), auto-detects the format
        from the image size.

        For hard disc images (``.dat``), requires a companion ``.dsc``
        sidecar file alongside it containing SCSI disc geometry.
        Either the ``.dat`` or ``.dsc`` file may be specified — the
        companion is located by swapping the extension.

        Args:
            filepath: Path to the disc image file.
            mode: ``"rb"`` for read-only (default), ``"r+b"`` for read-write.

        Yields:
            ADFS instance backed by the file.

        Raises:
            FileNotFoundError: If the file or its companion does not exist.
            ADFSError: If the image is not a valid ADFS disc.
        """
        if mode not in ("rb", "r+b"):
            raise ValueError(f"mode must be 'rb' or 'r+b', got {mode!r}")

        p = Path(filepath)
        ext = p.suffix.lower()

        if ext in (".dat", ".dsc"):
            # Hard disc image pair
            dat_filepath = p.with_suffix(".dat")
            dsc_filepath = p.with_suffix(".dsc")

            if not dat_filepath.exists():
                raise FileNotFoundError(
                    f"Hard disc data file not found: {dat_filepath}"
                )
            if not dsc_filepath.exists():
                raise FileNotFoundError(
                    f"Hard disc geometry file not found: {dsc_filepath}"
                )

            geometry = _parse_dsc(dsc_filepath)
            dat_size = dat_filepath.stat().st_size
            fmt = _hard_disc_format(geometry, dat_size)

            access = mmap.ACCESS_READ if mode == "rb" else mmap.ACCESS_WRITE
            dat_mode = mode if ext == ".dat" else "rb"
            with open(dat_filepath, dat_mode) as f:
                mm = mmap.mmap(f.fileno(), 0, access=access)
                adfs = ADFS._from_buffer_with_format(memoryview(mm), fmt)
                try:
                    yield adfs
                finally:
                    if dat_mode == "r+b":
                        mm.flush()
        else:
            # Floppy image
            access = mmap.ACCESS_READ if mode == "rb" else mmap.ACCESS_WRITE
            with open(filepath, mode) as f:
                mm = mmap.mmap(f.fileno(), 0, access=access)
                adfs = ADFS.from_buffer(memoryview(mm))
                try:
                    yield adfs
                finally:
                    if mode == "r+b":
                        mm.flush()

    @classmethod
    def from_buffer(cls, buffer: memoryview) -> ADFS:
        """Create ADFS from a buffer, auto-detecting format.

        For known floppy sizes (160KB, 320KB, 640KB), uses the
        corresponding ADFS S/M/L format.  For other sizes, treats
        the buffer as a flat hard disc image (single surface).

        Args:
            buffer: Disc image data.

        Returns:
            ADFS instance.

        Raises:
            ADFSError: If the image is not a valid ADFS disc.
        """
        buf_size = len(buffer)
        fmt = _ADFS_FORMATS_BY_SIZE.get(buf_size)
        if fmt is None:
            # Not a known floppy size — treat as flat hard disc image
            if buf_size % _ADFS_BYTES_PER_SECTOR != 0:
                raise ADFSError(
                    f"Buffer size ({buf_size}) is not a multiple "
                    f"of the sector size ({_ADFS_BYTES_PER_SECTOR})"
                )
            total_sectors = buf_size // _ADFS_BYTES_PER_SECTOR
            if total_sectors < _OLD_FSM_SECTORS + _OLD_DIR_SECTORS:
                raise ADFSError(
                    f"Buffer too small ({total_sectors} sectors) for ADFS "
                    f"(minimum {_OLD_FSM_SECTORS + _OLD_DIR_SECTORS} sectors)"
                )
            fmt = ADFSFormat(
                surface_specs=[SurfaceSpec(
                    num_tracks=1,
                    sectors_per_track=total_sectors,
                    bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
                    track_zero_offset_bytes=0,
                    track_stride_bytes=buf_size,
                )],
                total_sectors=total_sectors,
                total_bytes=buf_size,
                label="HardDisc",
            )
        return cls._from_buffer_with_format(buffer, fmt)

    @classmethod
    def _from_buffer_with_format(cls, buffer: memoryview, fmt: ADFSFormat) -> ADFS:
        """Create ADFS from a buffer with an explicit format."""
        disc_image = DiscImage(buffer, fmt.surface_specs)
        unified = UnifiedDisc(disc_image)

        # Read free space map from sectors 0-1
        map_data = unified.sector_range(0, 2)
        fsm = OldFreeSpaceMap(map_data)

        # Detect directory format from root signature
        dir_format = _detect_directory_format(unified)

        return cls(unified, dir_format, fsm)

    @classmethod
    def create(
        cls,
        adfs_format: ADFSFormat,
        *,
        title: str = "",
        boot_option: int = 0,
    ) -> ADFS:
        """Create a new in-memory ADFS disc image with an empty root directory.

        Args:
            adfs_format: ADFS format (ADFS_S, ADFS_M, or ADFS_L).
            title: Disc title (default empty).
            boot_option: Boot option 0–3 (default 0).

        Returns:
            ADFS instance backed by an in-memory buffer.
        """
        buffer = memoryview(bytearray(adfs_format.total_bytes))
        disc_image = DiscImage(buffer, adfs_format.surface_specs)
        unified = UnifiedDisc(disc_image)

        _initialise_old_free_space_map(
            unified, adfs_format.total_sectors, boot_option
        )
        _initialise_old_root_directory(unified, title)

        map_data = unified.sector_range(0, 2)
        fsm = OldFreeSpaceMap(map_data)
        dir_format = OldDirectoryFormat()

        return cls(unified, dir_format, fsm)

    @staticmethod
    @contextmanager
    def create_file(
        filepath: Union[str, PathLike],
        adfs_format: ADFSFormat,
        *,
        title: str = "",
        boot_option: int = 0,
    ) -> Iterator[ADFS]:
        """Create a new ADFS disc image file with an empty root directory.

        The file is created at *filepath* and opened read-write via mmap.
        Changes are flushed on exit.

        Args:
            filepath: Path for the new disc image file.
            adfs_format: ADFS format (ADFS_S, ADFS_M, or ADFS_L).
            title: Disc title (default empty).
            boot_option: Boot option 0–3 (default 0).

        Yields:
            ADFS instance backed by the file.
        """
        with open(filepath, "wb") as f:
            f.write(b"\x00" * adfs_format.total_bytes)

        with open(filepath, "r+b") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_WRITE)
            buffer = memoryview(mm)
            disc_image = DiscImage(buffer, adfs_format.surface_specs)
            unified = UnifiedDisc(disc_image)

            _initialise_old_free_space_map(
                unified, adfs_format.total_sectors, boot_option
            )
            _initialise_old_root_directory(unified, title)

            map_data = unified.sector_range(0, 2)
            fsm = OldFreeSpaceMap(map_data)
            dir_format = OldDirectoryFormat()

            adfs = ADFS(unified, dir_format, fsm)
            try:
                yield adfs
            finally:
                mm.flush()

    # --- Path factory ---

    @property
    def root(self) -> ADFSPath:
        """The root directory (``$``)."""
        return ADFSPath(self, "$")

    def path(self, path: str) -> ADFSPath:
        """Create an ADFSPath from a path string.

        Args:
            path: ADFS path string, e.g. ``"$.Games.Elite"`` or ``"$"``.
        """
        return ADFSPath(self, path)

    # --- Disc-level metadata ---

    @property
    def title(self) -> str:
        """Disc title (from root directory title field)."""
        root = self._read_root_directory()
        return root.title

    @property
    def boot_option(self) -> int:
        """Boot option (0–3)."""
        return self._fsm.boot_option

    @property
    def free_space(self) -> int:
        """Free space in bytes."""
        return self._fsm.free_space

    @property
    def total_size(self) -> int:
        """Total disc size in bytes."""
        return self._fsm.total_size

    @property
    def disc_name(self) -> str:
        """Disc name from the free space map."""
        return self._fsm.disc_name

    def validate(self) -> list[str]:
        """Validate filesystem integrity. Returns list of error messages."""
        errors = []
        errors.extend(self._fsm.validate())

        # Validate root directory is readable
        try:
            self._read_root_directory()
        except Exception as e:
            errors.append(f"Root directory: {e}")

        return errors

    # --- Bulk operations ---

    def export_all(
        self,
        target_dirpath: Union[str, PathLike],
        *,
        preserve_metadata: bool = True,
    ) -> None:
        """Export entire filesystem preserving directory structure.

        Args:
            target_dirpath: Host directory to export into.
            preserve_metadata: If True, write .inf sidecar files.
        """
        import pathlib

        target = pathlib.Path(target_dirpath)
        target.mkdir(parents=True, exist_ok=True)

        for dirpath, dirnames, filenames in self.root.walk():
            # Create subdirectories on host
            relative = dirpath.path.replace("$", "").lstrip(".")
            if relative:
                host_dir = target / relative.replace(".", "/")
            else:
                host_dir = target
            host_dir.mkdir(parents=True, exist_ok=True)

            for filename in filenames:
                adfs_path = dirpath / filename
                host_filepath = host_dir / filename
                adfs_path.export(host_filepath, preserve_metadata=preserve_metadata)

    # --- Pythonic protocols ---

    def __repr__(self) -> str:
        return (
            f"ADFS(disc_name={self.disc_name!r}, "
            f"total_size={self.total_size}, "
            f"free_space={self.free_space})"
        )

    # --- Internal helpers ---

    def _read_root_directory(self) -> _ADFSDirectory:
        """Read and parse the root directory."""
        return self._read_directory_at(_OLD_MAP_ROOT_SECTOR)

    def _read_directory_at(self, disc_address: int) -> _ADFSDirectory:
        """Read and parse a directory at the given sector address."""
        num_sectors = self._dir_format.size_in_sectors
        data = self._disc.sector_range(disc_address, num_sectors)
        return self._dir_format.parse(data, disc_address)

    def _read_file_data(self, entry: _ADFSDirectoryEntry) -> bytes:
        """Read file data for a directory entry."""
        start_sector = entry.start_sector
        num_sectors = (entry.length + _ADFS_BYTES_PER_SECTOR - 1) // _ADFS_BYTES_PER_SECTOR
        if num_sectors == 0:
            return b""
        data = self._disc.sector_range(start_sector, num_sectors)
        return data[:entry.length]


def _detect_directory_format(unified: UnifiedDisc) -> ADFSDirectoryFormat:
    """Detect the directory format by checking for known signatures.

    For old map discs, the root directory starts at sector 2 (offset 0x200).
    Check for "Hugo" at offset 0x201 (old directory) or "Nick" at 0x401 (new directory).

    Raises:
        ADFSError: If no valid directory signature is found.
    """
    # Check for old directory: "Hugo" at 0x201
    root_data = unified.sector_range(2, 5)
    sig = root_data[1:5]
    if sig == b"Hugo" or sig == b"Nick":
        return OldDirectoryFormat()

    raise ADFSError(
        f"Unrecognised ADFS directory format. "
        f"Expected 'Hugo' or 'Nick' at offset 0x201, got {sig!r}"
    )

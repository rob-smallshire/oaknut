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


# --- Known ADFS floppy image sizes ---
_ADFS_S_SIZE = 1 * 40 * 16 * 256   # 163840  (160 KB)
_ADFS_M_SIZE = 1 * 80 * 16 * 256   # 327680  (320 KB)
_ADFS_L_SIZE = 2 * 80 * 16 * 256   # 655360  (640 KB)

_ADFS_SECTORS_PER_TRACK = 16
_ADFS_BYTES_PER_SECTOR = 256

# Root directory sector address for old map formats
_OLD_MAP_ROOT_SECTOR = 2


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


def _make_single_sided_specs(
    num_tracks: int,
) -> list[SurfaceSpec]:
    """Create SurfaceSpecs for a single-sided ADFS floppy."""
    track_size = _ADFS_SECTORS_PER_TRACK * _ADFS_BYTES_PER_SECTOR
    return [
        SurfaceSpec(
            num_tracks=num_tracks,
            sectors_per_track=_ADFS_SECTORS_PER_TRACK,
            bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
            track_zero_offset_bytes=0,
            track_stride_bytes=track_size,
        )
    ]


def _make_interleaved_double_sided_specs(
    num_tracks: int,
) -> list[SurfaceSpec]:
    """Create SurfaceSpecs for an interleaved double-sided ADFS floppy."""
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


def _detect_surface_specs(buffer_size: int) -> list[SurfaceSpec]:
    """Detect ADFS format from image file size.

    Returns SurfaceSpecs appropriate for the image.

    Raises:
        ADFSError: If the size doesn't match any known ADFS floppy format.
    """
    if buffer_size == _ADFS_S_SIZE:
        return _make_single_sided_specs(40)
    elif buffer_size == _ADFS_M_SIZE:
        return _make_single_sided_specs(80)
    elif buffer_size == _ADFS_L_SIZE:
        return _make_interleaved_double_sided_specs(80)
    else:
        raise ADFSError(
            f"Unrecognised ADFS image size: {buffer_size} bytes. "
            f"Expected {_ADFS_S_SIZE} (S), {_ADFS_M_SIZE} (M), "
            f"or {_ADFS_L_SIZE} (L)."
        )


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

        Auto-detects the ADFS format from the image size and content.

        Args:
            filepath: Path to the disc image file (.adf, .adl, .dat).
            mode: ``"rb"`` for read-only (default), ``"r+b"`` for read-write.

        Yields:
            ADFS instance backed by the file.

        Raises:
            FileNotFoundError: If the file does not exist.
            ADFSError: If the image is not a valid ADFS disc.
        """
        if mode not in ("rb", "r+b"):
            raise ValueError(f"mode must be 'rb' or 'r+b', got {mode!r}")

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

        Args:
            buffer: Disc image data.

        Returns:
            ADFS instance.

        Raises:
            ADFSError: If the image is not a valid ADFS disc.
        """
        specs = _detect_surface_specs(len(buffer))
        disc_image = DiscImage(buffer, specs)
        unified = UnifiedDisc(disc_image)

        # Read free space map from sectors 0-1
        map_data = unified.sector_range(0, 2)
        fsm = OldFreeSpaceMap(map_data)

        # Detect directory format from root signature
        dir_format = _detect_directory_format(unified)

        return cls(unified, dir_format, fsm)

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

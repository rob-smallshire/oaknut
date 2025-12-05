"""Layer 4: High-level DFS filesystem interface.

This module provides a Pythonic interface to Acorn DFS disk images,
mirroring BBC Micro DFS star commands while following modern Python conventions.
"""

from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
import mmap
from pathlib import Path
from typing import Iterator, Optional, Union, TYPE_CHECKING

from oaknut_dfs.catalog import Catalog, AcornDFSCatalog, FileEntry
from oaknut_dfs.catalog import DiskInfo as CatalogDiskInfo
from oaknut_dfs.sector_image import (
    SectorImage,
    SSDSectorImage,
    InterleavedDSDSectorImage,
    SequentialDSDSectorImage,
    SSDSideSectorImage,
    DSDSideSectorImage,
)
from oaknut_dfs.exceptions import DiskFullError, FileLocked, InvalidFormatError

# Acorn DFS constants
ACORN_DFS_SECTORS_PER_TRACK = SectorImage.ACORN_DFS_SECTORS_PER_TRACK
SECTOR_SIZE = SectorImage.SECTOR_SIZE

if TYPE_CHECKING:
    from typing import Type


# Format strings for disk formats
FORMAT_SSD = "ssd"
FORMAT_DSD_INTERLEAVED = "dsd-interleaved"
FORMAT_DSD_SEQUENTIAL = "dsd-sequential"


class BootOption(IntEnum):
    """Disk boot options (*OPT 4,n).

    Controls behavior on SHIFT+BREAK:
    - NONE: No action
    - LOAD: *LOAD $.!BOOT (load to memory)
    - RUN: *RUN $.!BOOT (load and execute)
    - EXEC: *EXEC $.!BOOT (execute as keyboard input)
    """
    NONE = 0
    LOAD = 1
    RUN = 2
    EXEC = 3


@dataclass(frozen=True)
class FileInfo:
    """User-facing file information.

    This is the public API representation of a file, separate from
    the internal FileEntry used by the catalog layer.
    """
    name: str              # Full name including directory (e.g., "$.HELLO")
    filename: str          # Filename without directory
    directory: str         # Directory character
    locked: bool           # File is locked (cannot be modified/deleted)
    load_address: int      # Load address for machine code
    exec_address: int      # Execution address
    length: int            # Length in bytes
    start_sector: int      # Starting sector number

    @property
    def sectors(self) -> int:
        """Number of 256-byte sectors occupied by this file."""
        return (self.length + 255) // 256


@dataclass(frozen=True)
class DiskInfo:
    """User-facing disk information."""
    title: str             # Disk title (12 chars max)
    num_files: int         # Number of files in catalog
    total_sectors: int     # Total sectors on disk
    free_sectors: int      # Number of free sectors
    boot_option: BootOption  # Boot option setting
    format: str            # Format description (e.g., "SSD 40T")


class DFSImage:
    """
    High-level interface to Acorn DFS disk images.

    This class provides Pythonic access to DFS disk images, mirroring
    the BBC Micro's DFS star commands while following Python conventions.

    Basic usage:
        >>> with DFSImage.open("games.ssd") as disk:
        ...     print(disk.title)
        ...     data = disk.load("$.ELITE")

    Create new disks:
        >>> with DFSImage.create("new.ssd", title="MY DISK") as disk:
        ...     disk.save("$.HELLO", b"Hello, World!")

    Direct buffer access:
        >>> buffer = bytearray(204800)  # 200KB
        >>> disk = DFSImage(buffer, format="ssd")
        >>> disk.save("$.TEST", b"test data")
    """

    def __init__(self, buffer, *, format: str = "auto", side: int = 0):
        """
        Initialize DFS filesystem from a buffer.

        Args:
            buffer: Any buffer-protocol object (bytes, bytearray, memoryview, mmap)
            format: Format string ("ssd", "dsd-interleaved", "dsd-sequential", "auto")
            side: Which side to access (0 or 1) for double-sided formats

        Raises:
            ValueError: If format is invalid or side is out of range
            InvalidFormatError: If buffer size doesn't match format

        Example:
            >>> # From bytearray
            >>> buffer = bytearray(204800)
            >>> disk = DFSImage(buffer, format="ssd")

            >>> # From memoryview slice (e.g., MMB container)
            >>> mmb_view = memoryview(mmb_data)[offset:offset + 204800]
            >>> disk = DFSImage(mmb_view, format="ssd")
        """
        self._buffer = memoryview(buffer)
        self._format = format
        self._side = side
        self._current_directory = "$"

        # Detect format from size if auto
        if format == "auto":
            format = self._detect_format_from_size(len(self._buffer))
            self._format = format

        # Create sector image and catalog
        self._sector_image = self._create_sector_image(self._buffer, format, side)
        self._catalog = AcornDFSCatalog(self._sector_image)

    @classmethod
    @contextmanager
    def open(
        cls,
        filepath: Union[Path, str],
        *,
        mode: str = "r+b",
        format: str = "auto",
        side: int = 0,
    ):
        """
        Open an existing disk image with memory mapping.

        Auto-detects format from file extension and size:
        - .ssd -> Single-sided sequential
        - .dsd -> Double-sided interleaved (standard)

        For double-sided disks (DSD), each side has independent catalog:
        - side=0: First side (400 sectors, catalog at sectors 0-1)
        - side=1: Second side (400 sectors, catalog at sectors 0-1)

        Args:
            filepath: Path to disk image (.ssd or .dsd)
            mode: File mode ("r+b" for read-write, "rb" for read-only)
            format: Force format ("ssd", "dsd-interleaved", "dsd-sequential", "auto")
            side: Which side to access (0 or 1, default: 0)

        Yields:
            DFSImage instance

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid or unrecognized
            InvalidFormatError: If side=1 specified for SSD format

        Example:
            >>> with DFSImage.open("games.ssd") as disk:
            ...     print(disk.title)
            ...     data = disk.load("$.ELITE")

            >>> # Read-only access
            >>> with DFSImage.open("games.ssd", mode="rb") as disk:
            ...     files = disk.files

            >>> # Open specific side of DSD
            >>> with DFSImage.open("disk.dsd", side=1) as disk:
            ...     print(f"Side 1: {disk.title}")
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"Disk image not found: {filepath}")

        # Detect format from extension if auto
        if format == "auto":
            ext = filepath.suffix.lower()
            if ext == ".ssd":
                format = FORMAT_SSD
            elif ext == ".dsd":
                format = FORMAT_DSD_INTERLEAVED
            # else: will detect from size in __init__

        # Open file and create mmap
        file = open(filepath, mode)
        try:
            # Determine mmap access mode
            if "w" in mode or "+" in mode or "a" in mode:
                access = mmap.ACCESS_WRITE
            else:
                access = mmap.ACCESS_READ

            mm = mmap.mmap(file.fileno(), 0, access=access)
            # Create and yield DFSImage
            disk = cls(mm, format=format, side=side)
            yield disk
            # Note: we don't explicitly close mm - closing the file will flush and release it
        finally:
            file.close()

    @staticmethod
    def _detect_format_from_size(size: int) -> str:
        """Detect disk image format from buffer size."""
        # Validate size is a multiple of track size
        if size % 2560 != 0:
            raise InvalidFormatError(f"Invalid disk image size: {size} bytes")

        # Detect from size
        tracks = size // 2560
        if tracks in (40, 80):
            return FORMAT_SSD
        elif tracks in (80, 160):
            return FORMAT_DSD_INTERLEAVED
        else:
            raise InvalidFormatError(f"Unrecognized disk size: {size} bytes")

    @staticmethod
    def _create_sector_image(
        buffer, format: str, side: int = 0
    ) -> SectorImage:
        """
        Create appropriate sector image for format and side.

        Args:
            buffer: Buffer containing disk image data
            format: Format string ("ssd", "dsd-interleaved", "dsd-sequential")
            side: Which side to access (0 or 1, default: 0)

        Returns:
            SectorImage instance configured for the requested side

        Raises:
            InvalidFormatError: If format is unknown or side is invalid for format
            ValueError: If side is not 0 or 1
        """
        # Validate side parameter
        if side not in (0, 1):
            raise ValueError(f"Invalid side: {side} (must be 0 or 1)")

        # For now, we only support Acorn DFS (10 sectors per track)
        # Future formats like Watford DDFS would need to pass different values
        sectors_per_track = ACORN_DFS_SECTORS_PER_TRACK

        if format == FORMAT_SSD:
            # SSD only has side 0
            if side != 0:
                raise InvalidFormatError(
                    f"SSD format only supports side=0, got side={side}"
                )
            ssd_img = SSDSectorImage(buffer, sectors_per_track)
            # Calculate tracks from buffer size
            tracks_per_side = len(buffer) // (sectors_per_track * SECTOR_SIZE)
            return SSDSideSectorImage(ssd_img, 0, tracks_per_side)

        elif format == FORMAT_DSD_INTERLEAVED:
            # DSD supports both sides
            size = len(buffer)
            total_tracks = size // (sectors_per_track * SECTOR_SIZE)
            tracks_per_side = total_tracks // 2

            # Create interleaved image, then wrap for specific side
            interleaved = InterleavedDSDSectorImage(buffer, tracks_per_side, sectors_per_track)
            return DSDSideSectorImage(interleaved, side, tracks_per_side)

        elif format == FORMAT_DSD_SEQUENTIAL:
            # Sequential DSD also supports both sides
            size = len(buffer)
            total_tracks = size // (sectors_per_track * SECTOR_SIZE)
            tracks_per_side = total_tracks // 2

            # Create sequential image, then wrap for specific side
            sequential = SequentialDSDSectorImage(buffer, sectors_per_track)
            return DSDSideSectorImage(sequential, side, tracks_per_side)

        else:
            raise InvalidFormatError(f"Unknown format: {format}")

    @classmethod
    @contextmanager
    def create(
        cls,
        filepath: Union[Path, str],
        *,
        title: str = "",
        num_tracks_per_side: int = 40,
        format: str = "auto",
    ):
        """
        Create a new formatted disk image file.

        Args:
            filepath: Path for new disk image file
            title: Disk title (max 12 chars, default: derived from filename)
            num_tracks_per_side: Number of tracks per side (40 or 80, default: 40)
            format: Format ("ssd", "dsd-interleaved", "dsd-sequential", or "auto")

        Yields:
            DFSImage instance

        Raises:
            FileExistsError: If file already exists
            ValueError: If parameters are invalid

        Example:
            >>> with DFSImage.create("new.ssd", title="MY DISK") as disk:
            ...     disk.save("$.HELLO", b"Hello!")

            >>> # 80-track disk
            >>> with DFSImage.create("big.ssd", num_tracks_per_side=80) as disk:
            ...     print(f"{disk.info.num_sectors} sectors")
        """
        filepath = Path(filepath)

        if filepath.exists():
            raise FileExistsError(f"File already exists: {filepath}")

        # Default title from filename
        if not title:
            title = filepath.stem.upper()[:12]

        # Detect format from extension if auto
        if format == "auto":
            ext = filepath.suffix.lower()
            if ext == ".ssd":
                format = FORMAT_SSD
            elif ext == ".dsd":
                format = FORMAT_DSD_INTERLEAVED
            else:
                raise ValueError(
                    f"Cannot auto-detect format from extension '{ext}'. "
                    f"Specify format parameter."
                )

        # Calculate size and number of sides
        # For now, only Acorn DFS with 10 sectors per track
        sectors_per_track = ACORN_DFS_SECTORS_PER_TRACK

        if format == FORMAT_SSD:
            size = num_tracks_per_side * sectors_per_track * SECTOR_SIZE
            num_sides = 1
        elif format in (FORMAT_DSD_INTERLEAVED, FORMAT_DSD_SEQUENTIAL):
            size = num_tracks_per_side * 2 * sectors_per_track * SECTOR_SIZE
            num_sides = 2
        else:
            raise ValueError(f"Unknown format: {format}")

        # Create empty file of correct size
        with open(filepath, "wb") as f:
            f.write(b"\x00" * size)

        # Open with mmap and initialize catalogs
        with cls.open(filepath, mode="r+b", format=format, side=0) as disk:
            # Initialize catalogs for all sides
            for side_num in range(num_sides):
                if side_num > 0:
                    # Create sector image for this side
                    sector_img = disk._create_sector_image(disk._buffer, format, side_num)
                    catalog = AcornDFSCatalog(sector_img)
                else:
                    catalog = disk._catalog

                # Initialize empty catalog
                catalog.write_disk_info(CatalogDiskInfo(
                    title=title,
                    cycle_number=0,
                    num_files=0,
                    total_sectors=num_tracks_per_side * sectors_per_track,
                    boot_option=0,
                ))

            yield disk

    @classmethod
    def from_bytes(cls, data: bytes, *, format: str = "auto", side: int = 0) -> "DFSImage":
        """
        Create DFS filesystem from bytes (makes a mutable copy).

        Useful for testing or temporary in-memory modifications.

        Args:
            data: Disk image bytes
            format: Format string or "auto" to detect from size
            side: Which side to access (0 or 1)

        Returns:
            DFSImage instance backed by bytearray

        Example:
            >>> with open("disk.ssd", "rb") as f:
            ...     data = f.read()
            >>>
            >>> disk = DFSImage.from_bytes(data)
            >>> disk.save("$.TEST", b"test")
            >>>
            >>> # Get modified bytes back
            >>> modified = bytes(disk._buffer)
        """
        buffer = bytearray(data)
        return cls(buffer, format=format, side=side)

    def load(self, filename: str) -> bytes:
        """
        Load file data from disk (*LOAD equivalent).

        Args:
            filename: Full filename (e.g., "$.HELLO" or "A.PROGRAM")
                     Directory can be omitted to use current directory

        Returns:
            File data as bytes

        Raises:
            FileNotFoundError: If file doesn't exist

        Example:
            >>> data = disk.load("$.ELITE")
            >>> code = disk.load("PROGRAM")  # Uses current directory
        """
        full_name = self._resolve_filename(filename)
        entry = self._catalog.find_file(full_name)

        if entry is None:
            disk_name = f" on disk '{self._filepath}'" if self._filepath else ""
            raise FileNotFoundError(f"File '{full_name}' not found{disk_name}")

        # Get all sectors for the file at once
        sectors_view = self._sector_image.get_sectors(
            entry.start_sector, entry.sectors_required
        )

        # Return only actual file data (trim padding)
        return bytes(sectors_view[: entry.length])

    def exists(self, filename: str) -> bool:
        """
        Check if file exists on disk.

        Args:
            filename: File to check

        Returns:
            True if file exists, False otherwise

        Example:
            >>> if disk.exists("$.CONFIG"):
            ...     data = disk.load("$.CONFIG")
        """
        full_name = self._resolve_filename(filename)
        return self._catalog.find_file(full_name) is not None

    def get_file_info(self, filename: str) -> FileInfo:
        """
        Get detailed information about a file (*INFO equivalent).

        Args:
            filename: File to query

        Returns:
            FileInfo with file metadata

        Raises:
            FileNotFoundError: If file doesn't exist

        Example:
            >>> info = disk.get_file_info("$.HELLO")
            >>> print(f"Load addr: 0x{info.load_address:X}")
            >>> print(f"Locked: {info.locked}")
        """
        full_name = self._resolve_filename(filename)
        entry = self._catalog.find_file(full_name)

        if entry is None:
            raise FileNotFoundError(f"File not found: {full_name}")

        return self._entry_to_fileinfo(entry)

    @property
    def files(self) -> list[FileInfo]:
        """
        Get list of all files on disk (*CAT equivalent).

        Returns:
            List of FileInfo for all files

        Example:
            >>> print(f"Disk has {len(disk.files)} files")
            >>> for f in disk.files:
            ...     print(f"{f.name:12} {f.length:6} bytes")
        """
        return [self._entry_to_fileinfo(e) for e in self._catalog.list_files()]

    @property
    def title(self) -> str:
        """
        Get disk title.

        Example:
            >>> print(disk.title)
            GAMES DISK
        """
        return self._catalog.read_disk_info().title

    @title.setter
    def title(self, new_title: str) -> None:
        """
        Set disk title (*TITLE equivalent).

        Args:
            new_title: New disk title (max length depends on catalog type)

        Raises:
            ValueError: If title is invalid or too long

        Example:
            >>> disk.title = "MY DISK"
        """
        info = self._catalog.read_disk_info()
        info.title = new_title
        self._catalog.write_disk_info(info)  # Catalog validates title length

    @property
    def boot_option(self) -> BootOption:
        """
        Get boot option (*OPT 4 equivalent).

        Returns:
            BootOption enum value

        Example:
            >>> if disk.boot_option == BootOption.EXEC:
            ...     print("Disk will EXEC !BOOT on startup")
        """
        return BootOption(self._catalog.read_disk_info().boot_option)

    @boot_option.setter
    def boot_option(self, option: Union[BootOption, int]) -> None:
        """
        Set boot option (*OPT 4,n equivalent).

        Args:
            option: Boot option (0-3 or BootOption enum)

        Raises:
            ValueError: If option is invalid

        Example:
            >>> disk.boot_option = BootOption.EXEC
            >>> disk.boot_option = 3  # Same as above
        """
        if isinstance(option, int):
            if option not in (0, 1, 2, 3):
                raise ValueError(f"Boot option must be 0-3, got {option}")
            option = BootOption(option)

        info = self._catalog.read_disk_info()
        info.boot_option = option.value
        self._catalog.write_disk_info(info)

    @property
    def free_sectors(self) -> int:
        """
        Calculate free space in sectors (*FREE equivalent).

        Returns:
            Number of free sectors

        Example:
            >>> free_kb = disk.free_sectors * 256 // 1024
            >>> print(f"{free_kb} KB free")
        """
        catalog_info = self._catalog.read_disk_info()
        files = self._catalog.list_files()

        # Build map of used sectors
        used = set(range(2))  # Sectors 0-1 are catalog

        for entry in files:
            for i in range(entry.sectors_required):
                used.add(entry.start_sector + i)

        return catalog_info.total_sectors - len(used)

    @property
    def info(self) -> DiskInfo:
        """
        Get disk information (*INFO equivalent).

        Returns:
            DiskInfo with disk metadata

        Example:
            >>> info = disk.info
            >>> print(f"Title: {info.title}")
            >>> print(f"Files: {info.num_files}/{31}")
            >>> print(f"Free: {info.free_sectors} sectors")
        """
        catalog_info = self._catalog.read_disk_info()

        return DiskInfo(
            title=catalog_info.title,
            num_files=catalog_info.num_files,
            total_sectors=catalog_info.total_sectors,
            free_sectors=self.free_sectors,
            boot_option=BootOption(catalog_info.boot_option),
            format=self._sector_image.format_description(),
        )

    def __contains__(self, filename: str) -> bool:
        """
        Check if file exists (enables 'in' operator).

        Example:
            >>> if "$.HELLO" in disk:
            ...     print("File exists")
        """
        return self.exists(filename)

    def __iter__(self) -> Iterator[FileInfo]:
        """
        Iterate over files (enables 'for file in disk').

        Example:
            >>> for file in disk:
            ...     print(file.name)
        """
        return iter(self.files)

    def __len__(self) -> int:
        """
        Get number of files (enables len(disk)).

        Example:
            >>> print(f"Disk has {len(disk)} files")
        """
        return len(self.files)

    def __repr__(self) -> str:
        """String representation for debugging."""
        info = self.info
        path = f" at {self._filepath}" if self._filepath else ""
        return (
            f"DFSImage(title='{info.title}', "
            f"files={info.num_files}, "
            f"format={info.format}{path})"
        )

    def __str__(self) -> str:
        """User-friendly string representation."""
        info = self.info
        return (
            f"DFS Disk '{info.title}' ({info.format}): "
            f"{info.num_files} files, {info.free_sectors} sectors free"
        )

    def change_directory(self, directory: str) -> None:
        """
        Change current directory (*DIR equivalent).

        Args:
            directory: Single character directory name ($, A-Z)

        Raises:
            ValueError: If directory character is invalid

        Example:
            >>> disk.change_directory("A")
            >>> disk.save("PROG", data)  # Saves as "A.PROG"
        """
        if len(directory) != 1:
            raise ValueError(f"Directory must be single character: {directory}")

        self._current_directory = directory.upper()

    @property
    def current_directory(self) -> str:
        """Get current directory character."""
        return self._current_directory

    def list_directory(self, directory: Optional[str] = None) -> list[FileInfo]:
        """
        List files in a directory (*CAT equivalent).

        Args:
            directory: Directory to list (default: current directory)

        Returns:
            List of FileInfo for files in directory

        Example:
            >>> for file in disk.list_directory("$"):
            ...     print(file.name)
        """
        dir_char = directory.upper() if directory else self._current_directory

        all_files = [self._entry_to_fileinfo(e) for e in self._catalog.list_files()]
        return [f for f in all_files if f.directory == dir_char]

    def validate(self) -> list[str]:
        """
        Validate disk integrity (*VERIFY equivalent).

        Checks:
        - Catalog structure validity
        - File entries don't overlap
        - Files don't exceed disk bounds
        - No duplicate filenames

        Returns:
            List of error messages (empty if disk is valid)

        Example:
            >>> errors = disk.validate()
            >>> if errors:
            ...     for error in errors:
            ...         print(f"ERROR: {error}")
            >>> else:
            ...     print("Disk is valid")
        """
        errors = self._catalog.validate()

        # Additional validation: check for overlapping files
        files = self._catalog.list_files()
        sector_map = {}  # sector -> filename

        for entry in files:
            for i in range(entry.sectors_required):
                sector = entry.start_sector + i
                if sector in sector_map:
                    errors.append(
                        f"Files overlap at sector {sector}: "
                        f"{sector_map[sector]} and {entry.full_name}"
                    )
                sector_map[sector] = entry.full_name

        return errors

    def _resolve_filename(self, filename: str) -> str:
        """Resolve filename, adding current directory if needed."""
        if "." not in filename:
            return f"{self._current_directory}.{filename}"
        return filename.upper()

    @classmethod
    @contextmanager
    def create(
        cls,
        filepath: Union[Path, str],
        *,
        title: str = "",
        num_tracks_per_side: int = 40,
        format: Optional[str] = None,
        side: int = 0,
    ):
        """
        Create a new formatted disk image (*FORM equivalent).

        Returns a context manager that automatically closes the file.

        Args:
            filepath: Path for new disk image
            title: Disk title (max 12 chars, default: derived from filename)
            num_tracks_per_side: Number of tracks per side (40 or 80, default: 40)
            format: Disk format string ("ssd", "dsd-interleaved", "dsd-sequential", default: auto-detect from extension)
            side: Which side to access for DSD (0 or 1, default: 0)

        Yields:
            DFSImage instance with empty catalog

        Raises:
            ValueError: If parameters are invalid
            FileExistsError: If file already exists

        Example:
            >>> with DFSImage.create("new.ssd", title="MY DISK") as disk:
            ...     disk.save("$.TEST", b"test data")

            >>> # 80 track disk
            >>> with DFSImage.create("new.ssd", num_tracks_per_side=80) as disk:
            ...     pass

            >>> # Explicitly specify format
            >>> with DFSImage.create("new.dsd", format="dsd-sequential") as disk:
            ...     pass
        """
        filepath = Path(filepath)

        if filepath.exists():
            raise FileExistsError(f"File already exists: {filepath}")

        # Default title from filename
        if not title:
            title = filepath.stem.upper()[:12]

        # Auto-detect format from extension if not specified
        if format is None:
            ext = filepath.suffix.lower()
            if ext == ".ssd":
                format = FORMAT_SSD
            elif ext == ".dsd":
                format = FORMAT_DSD_INTERLEAVED
            else:
                raise ValueError(
                    f"Cannot auto-detect format from extension '{ext}'. "
                    f"Please specify format parameter (e.g., format='ssd')"
                )

        # Calculate file size based on format and tracks
        sectors_per_track = 10  # Standard Acorn DFS
        if format == FORMAT_SSD:
            num_sectors = num_tracks_per_side * sectors_per_track
        elif format in (FORMAT_DSD_INTERLEAVED, FORMAT_DSD_SEQUENTIAL):
            num_sectors = 2 * num_tracks_per_side * sectors_per_track
        else:
            raise ValueError(f"Unknown format: {format}")

        file_size = num_sectors * 256  # 256 bytes per sector

        # Create the file with zeros
        file = open(filepath, "w+b")
        try:
            file.write(bytes(file_size))
            file.flush()

            # Memory-map it
            mm = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_WRITE)
            # Create DFSImage instance
            disk = cls(mm, format=format, side=side)

            # Initialize catalog with empty disk info
            disk_info = CatalogDiskInfo(
                title=title,
                cycle_number=0,
                num_files=0,
                total_sectors=disk._sector_image.num_sectors(),
                boot_option=0,
            )
            disk._catalog.write_disk_info(disk_info)

            yield disk
            # Note: we don't explicitly close mm - closing the file will flush and release it
        finally:
            file.close()

    def save(
        self,
        filename: str,
        data: bytes,
        *,
        load_address: int = 0,
        exec_address: int = 0,
        locked: bool = False,
        overwrite: bool = True,
    ) -> None:
        """
        Save file to disk (*SAVE equivalent).

        Args:
            filename: Full filename including directory (e.g., "$.HELLO")
            data: File data as bytes
            load_address: Load address for machine code (default: 0)
            exec_address: Execution address (default: 0)
            locked: Lock file after saving (default: False)
            overwrite: Overwrite if exists (default: True)

        Raises:
            ValueError: If disk is full or filename invalid
            FileExistsError: If file exists and overwrite=False
            PermissionError: If overwriting locked file

        Example:
            >>> disk.save("$.HELLO", b"Hello, World!")
            >>> disk.save("$.CODE", code_bytes,
            ...          load_address=0x1900, exec_address=0x1900)
        """
        full_name = self._resolve_filename(filename)

        # Validate filename format
        if "." not in full_name:
            raise ValueError(f"Filename must include directory: {filename}")

        directory, name = full_name.split(".", 1)

        if len(name) > 7:
            raise ValueError(f"Filename too long (max 7 chars): {name}")

        if len(directory) != 1:
            raise ValueError(f"Directory must be single character: {directory}")

        # Check if file exists
        existing = self._catalog.find_file(full_name)
        if existing:
            if not overwrite:
                raise FileExistsError(f"File already exists: {full_name}")
            if existing.locked:
                raise FileLocked(f"Cannot overwrite locked file: {full_name}")
            # Delete existing file first
            self.delete(full_name)

        # Find free space
        start_sector = self._find_free_space(len(data))

        if start_sector is None:
            needed = (len(data) + 255) // 256
            free = self.free_sectors
            raise DiskFullError(
                f"Cannot save '{full_name}': needs {needed} sectors, "
                f"only {free} free"
            )

        # Write data to sectors
        sectors_needed = (len(data) + 255) // 256
        sectors_view = self._sector_image.get_sectors(start_sector, sectors_needed)

        # Pad data to sector boundary and write
        padded_data = data + bytes(sectors_needed * 256 - len(data))
        sectors_view[:] = padded_data

        # Add catalog entry
        entry = FileEntry(
            filename=name.ljust(7),
            directory=directory,
            locked=locked,
            load_address=load_address,
            exec_address=exec_address,
            length=len(data),
            start_sector=start_sector,
        )
        self._catalog.add_file_entry(entry)

    def delete(self, filename: str) -> None:
        """
        Delete file from disk (*DELETE equivalent).

        Args:
            filename: Full filename to delete

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file is locked

        Example:
            >>> disk.delete("$.OLDFILE")
        """
        full_name = self._resolve_filename(filename)
        self._catalog.remove_file_entry(full_name)

    def rename(self, old_name: str, new_name: str) -> None:
        """
        Rename a file (*RENAME equivalent).

        Args:
            old_name: Current filename
            new_name: New filename

        Raises:
            FileNotFoundError: If old file doesn't exist
            FileExistsError: If new filename already exists
            PermissionError: If file is locked
            ValueError: If new filename is invalid

        Example:
            >>> disk.rename("$.OLD", "$.NEW")
        """
        old_full = self._resolve_filename(old_name)
        new_full = self._resolve_filename(new_name)

        # Get existing file
        entry = self._catalog.find_file(old_full)
        if entry is None:
            raise FileNotFoundError(f"File not found: {old_full}")

        if entry.locked:
            raise FileLocked(f"Cannot rename locked file: {old_full}")

        # Check new name doesn't exist
        if self._catalog.find_file(new_full) is not None:
            raise FileExistsError(f"File already exists: {new_full}")

        # Parse new name
        if "." not in new_full:
            raise ValueError(f"Filename must include directory: {new_name}")

        new_dir, new_file = new_full.split(".", 1)

        if len(new_file) > 7:
            raise ValueError(f"Filename too long (max 7 chars): {new_file}")

        # Load data, delete old, save with new name
        data = self.load(old_full)
        self._catalog.remove_file_entry(old_full)

        new_entry = FileEntry(
            filename=new_file.ljust(7),
            directory=new_dir,
            locked=entry.locked,
            load_address=entry.load_address,
            exec_address=entry.exec_address,
            length=entry.length,
            start_sector=entry.start_sector,
        )
        self._catalog.add_file_entry(new_entry)

    def lock(self, filename: str) -> None:
        """
        Lock a file to prevent deletion/modification (*ACCESS <file> L).

        Args:
            filename: File to lock

        Raises:
            FileNotFoundError: If file doesn't exist

        Example:
            >>> disk.lock("$.IMPORTANT")
        """
        self._set_locked(filename, True)

    def unlock(self, filename: str) -> None:
        """
        Unlock a file (*ACCESS <file>).

        Args:
            filename: File to unlock

        Raises:
            FileNotFoundError: If file doesn't exist

        Example:
            >>> disk.unlock("$.EDITABLE")
        """
        self._set_locked(filename, False)

    def _find_free_space(self, data_length: int) -> Optional[int]:
        """Find contiguous free space for file."""
        sectors_needed = (data_length + 255) // 256
        free_map = self.get_free_map()

        # Search for first region with enough space
        for start_sector, length in free_map:
            if length >= sectors_needed:
                return start_sector

        return None  # Disk full

    def get_free_map(self) -> list[tuple[int, int]]:
        """
        Get free space map (*MAP equivalent).

        Returns:
            List of (start_sector, length) tuples for free regions

        Example:
            >>> for start, length in disk.get_free_map():
            ...     print(f"Free: sector {start:03X}, {length} sectors")
        """
        catalog_info = self._catalog.read_disk_info()
        files = self._catalog.list_files()

        # Build map of used sectors
        used = set(range(2))  # Catalog
        for entry in files:
            for i in range(entry.sectors_required):
                used.add(entry.start_sector + i)

        # Find contiguous free regions
        free_regions = []
        start = None

        for sector in range(catalog_info.total_sectors):
            if sector not in used:
                if start is None:
                    start = sector
            else:
                if start is not None:
                    free_regions.append((start, sector - start))
                    start = None

        if start is not None:
            free_regions.append((start, catalog_info.total_sectors - start))

        return free_regions

    def compact(self) -> int:
        """
        Defragment disk by moving files to eliminate gaps (*COMPACT equivalent).

        Moves all files to the start of the disk, leaving all free space
        at the end in one contiguous block.

        Returns:
            Number of files moved

        Raises:
            PermissionError: If any file is locked

        Example:
            >>> moved = disk.compact()
            >>> print(f"Moved {moved} files")
        """
        files = self._catalog.list_files()

        # Check no files are locked
        for entry in files:
            if entry.locked:
                raise PermissionError(
                    f"Cannot compact: file '{entry.full_name}' is locked"
                )

        # Sort files by start sector
        files.sort(key=lambda e: e.start_sector)

        next_sector = 2  # Start after catalog
        moved = 0

        for entry in files:
            if entry.start_sector != next_sector:
                # Need to move this file
                # Read from old location
                old_sectors = self._sector_image.get_sectors(
                    entry.start_sector, entry.sectors_required
                )
                data = old_sectors.tobytes()

                # Write to new location
                new_sectors = self._sector_image.get_sectors(
                    next_sector, entry.sectors_required
                )
                new_sectors[:] = data

                # Update catalog entry
                entry.start_sector = next_sector
                moved += 1

            next_sector += entry.sectors_required

        # Rebuild catalog with updated entries
        if moved > 0:
            # Clear catalog
            catalog_info = self._catalog.read_disk_info()
            catalog_info.num_files = 0
            self._catalog.write_disk_info(catalog_info)

            # Re-add all files
            for entry in files:
                self._catalog.add_file_entry(entry)


        return moved

    def copy_file(self, source_filename: str, dest_filename: str) -> None:
        """
        Copy a file within the disk.

        Args:
            source_filename: Source file
            dest_filename: Destination filename

        Raises:
            FileNotFoundError: If source doesn't exist
            FileExistsError: If destination exists
            ValueError: If disk is full

        Example:
            >>> disk.copy_file("$.ORIG", "$.BACKUP")
        """
        info = self.get_file_info(source_filename)
        data = self.load(source_filename)

        self.save(
            dest_filename,
            data,
            load_address=info.load_address,
            exec_address=info.exec_address,
            locked=info.locked,
        )

    def save_text(
        self, filename: str, text: str, *, encoding: str = "utf-8", **save_kwargs
    ) -> None:
        """
        Save text file to disk (convenience wrapper).

        Args:
            filename: Full filename
            text: Text content (will be encoded to bytes)
            encoding: Text encoding (default: utf-8)
            **save_kwargs: Additional arguments for save()

        Example:
            >>> disk.save_text("$.!BOOT", "*RUN $.MAIN")
        """
        data = text.encode(encoding)
        self.save(filename, data, **save_kwargs)

    def save_from_file(
        self, filename: str, source_path: Union[Path, str], **save_kwargs
    ) -> None:
        """
        Save file from host filesystem to disk (convenience wrapper).

        Args:
            filename: DFS filename
            source_path: Path to source file on host system
            **save_kwargs: Additional arguments for save()

        Example:
            >>> disk.save_from_file("$.GAME", "build/game.bin",
            ...                     load_address=0x1900, exec_address=0x1900)
        """
        with open(source_path, "rb") as f:
            data = f.read()
        self.save(filename, data, **save_kwargs)

    def export_all(
        self, target_dir: Union[Path, str], *, preserve_metadata: bool = True
    ) -> None:
        """
        Export all files to host filesystem.

        Args:
            target_dir: Directory to export files to
            preserve_metadata: Create .inf files with metadata

        Example:
            >>> disk.export_all("exported/")
            # Creates: exported/$.HELLO, exported/$.GAME, etc.
            # With metadata files: exported/$.HELLO.inf
        """
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        for file in self.files:
            # Export data
            data = self.load(file.name)
            output_path = target_dir / file.name

            with open(output_path, "wb") as f:
                f.write(data)

            # Export metadata if requested
            if preserve_metadata:
                inf_path = target_dir / f"{file.name}.inf"
                with open(inf_path, "w") as f:
                    locked_str = " Locked" if file.locked else ""
                    f.write(
                        f"{file.name}   "
                        f"{file.load_address:08X} "
                        f"{file.exec_address:08X} "
                        f"{file.length:06X}{locked_str}\n"
                    )

    def import_from_inf(
        self,
        data_path: Union[Path, str],
        inf_path: Optional[Union[Path, str]] = None,
    ) -> None:
        """
        Import file from host filesystem with .inf metadata.

        Args:
            data_path: Path to file data
            inf_path: Path to .inf file (default: data_path + ".inf")

        Example:
            >>> disk.import_from_inf("game.bin", "game.inf")
            # Reads metadata from game.inf
        """
        data_path = Path(data_path)
        inf_path = (
            Path(inf_path)
            if inf_path
            else data_path.with_suffix(data_path.suffix + ".inf")
        )

        # Read data
        with open(data_path, "rb") as f:
            data = f.read()

        # Parse .inf file
        if inf_path.exists():
            with open(inf_path, "r") as f:
                line = f.readline().strip()
                parts = line.split()

                filename = parts[0]
                load_addr = int(parts[1], 16) if len(parts) > 1 else 0
                exec_addr = int(parts[2], 16) if len(parts) > 2 else 0
                # Check if "Locked" appears anywhere in remaining parts
                locked = any("Lock" in part for part in parts[3:]) if len(parts) > 3 else False
        else:
            # Use filename from data file
            filename = f"$.{data_path.stem.upper()[:7]}"
            load_addr = 0
            exec_addr = 0
            locked = False

        self.save(
            filename, data, load_address=load_addr, exec_address=exec_addr, locked=locked
        )

    @classmethod
    @contextmanager
    def create_from_files(
        cls,
        filepath: Union[Path, str],
        files: dict[str, Union[bytes, Path, dict]],
        *,
        title: str = "",
        **create_kwargs,
    ):
        """
        Create a new disk and populate with files in one operation.

        Convenience method for building disk images programmatically.
        Returns a context manager like create().

        Args:
            filepath: Path for new disk image
            files: Dict mapping DFS filenames to data (bytes, Path, or dict with 'data' and metadata)
            title: Disk title
            **create_kwargs: Additional arguments for create()

        Yields:
            DFSImage instance

        Example:
            >>> with DFSImage.create_from_files(
            ...     "game.ssd",
            ...     {
            ...         "$.!BOOT": b"*RUN $.MAIN",
            ...         "$.MAIN": Path("build/main.bin"),
            ...         "$.DATA": {"data": b"game data", "load_address": 0x1900}
            ...     },
            ...     title="MY GAME"
            ... ) as disk:
            ...     # Disk is already populated with files
            ...     print(f"Created disk with {len(disk.files)} files")
        """
        with cls.create(filepath, title=title, **create_kwargs) as disk:
            for name, content in files.items():
                if isinstance(content, dict):
                    # Dict format with metadata
                    data = content["data"]
                    save_kwargs = {k: v for k, v in content.items() if k != "data"}
                    disk.save(name, data, **save_kwargs)
                elif isinstance(content, Path):
                    # Path to file
                    with open(content, "rb") as f:
                        data = f.read()
                    disk.save(name, data)
                else:
                    # Raw bytes
                    disk.save(name, content)

            yield disk

    def _set_locked(self, filename: str, locked: bool) -> None:
        """Set locked status for a file."""
        full_name = self._resolve_filename(filename)
        entry = self._catalog.find_file(full_name)

        if entry is None:
            raise FileNotFoundError(f"File not found: {full_name}")

        # Update entry
        entry.locked = locked

        # Rebuild catalog (Layer 3 doesn't have update-in-place)
        files = [
            e for e in self._catalog.list_files() if e.full_name != full_name
        ]
        files.append(entry)

        # Clear and rebuild catalog
        catalog_info = self._catalog.read_disk_info()
        catalog_info.num_files = 0
        self._catalog.write_disk_info(catalog_info)

        for file_entry in files:
            self._catalog.add_file_entry(file_entry)


    @staticmethod
    def _entry_to_fileinfo(entry: FileEntry) -> FileInfo:
        """Convert catalog FileEntry to user-facing FileInfo."""
        return FileInfo(
            name=entry.full_name,
            filename=entry.filename.rstrip(),
            directory=entry.directory,
            locked=entry.locked,
            load_address=entry.load_address,
            exec_address=entry.exec_address,
            length=entry.length,
            start_sector=entry.start_sector,
        )

"""Layer 4: High-level DFS filesystem interface.

This module provides a Pythonic interface to Acorn DFS disk images,
mirroring BBC Micro DFS star commands while following modern Python conventions.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Iterator, Optional, Union

from oaknut_dfs.catalog import Catalog, AcornDFSCatalog, FileEntry
from oaknut_dfs.catalog import DiskInfo as CatalogDiskInfo
from oaknut_dfs.sector_image import (
    SectorImage,
    SSDSectorImage,
    InterleavedDSDSectorImage,
    SequentialDSDSectorImage,
)
from oaknut_dfs.disk_image import DiskImage, FileDiskImage, MemoryDiskImage


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


@dataclass
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


@dataclass
class DiskInfo:
    """User-facing disk information."""
    title: str             # Disk title (12 chars max)
    num_files: int         # Number of files in catalog
    total_sectors: int     # Total sectors on disk
    free_sectors: int      # Number of free sectors
    boot_option: BootOption  # Boot option setting
    format: str            # Format description (e.g., "SSD 40T")


class DFSFilesystem:
    """
    High-level interface to Acorn DFS disk images.

    This class provides Pythonic access to DFS disk images, mirroring
    the BBC Micro's DFS star commands while following Python conventions.

    Basic usage:
        >>> with DFSFilesystem.open("games.ssd") as disk:
        ...     print(disk.title)
        ...     data = disk.load("$.ELITE")

    Create new disks:
        >>> disk = DFSFilesystem.create("new.ssd", title="MY DISK")
        >>> disk.save("$.HELLO", b"Hello, World!")
        >>> disk.close()
    """

    def __init__(
        self,
        catalog: Catalog,
        sector_image: SectorImage,
        filepath: Optional[Path] = None,
    ):
        """
        Initialize DFS filesystem (use open() or create() instead).

        Args:
            catalog: Catalog layer instance
            sector_image: Sector access layer instance
            filepath: Optional path to disk image file
        """
        self._catalog = catalog
        self._sector_image = sector_image
        self._filepath = filepath
        self._current_directory = "$"
        self._dirty = False

    @classmethod
    def open(
        cls,
        filepath: Union[Path, str],
        *,
        writable: bool = True,
        format: Optional[str] = None,
    ) -> "DFSFilesystem":
        """
        Open an existing disk image.

        Auto-detects format from file extension and size:
        - .ssd -> Single-sided sequential
        - .dsd -> Double-sided interleaved (standard)
        - Format can be overridden with format parameter

        Args:
            filepath: Path to disk image (.ssd or .dsd)
            writable: Open for writing (default: True)
            format: Force format ("ssd", "dsd-interleaved", "dsd-sequential")

        Returns:
            DFSFilesystem instance

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid or unrecognized

        Example:
            >>> disk = DFSFilesystem.open("games.ssd")
            >>> print(disk.title)
            GAMES DISK
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"Disk image not found: {filepath}")

        # Auto-detect or use specified format
        detected_format = format or cls._detect_format(filepath)

        # Create appropriate layer stack
        if writable:
            disk_image = FileDiskImage(filepath)
        else:
            # Read into memory for read-only access
            with open(filepath, "rb") as f:
                disk_image = MemoryDiskImage(data=f.read())

        sector_image = cls._create_sector_image(disk_image, detected_format)
        catalog = AcornDFSCatalog(sector_image)

        return cls(catalog, sector_image, filepath if writable else None)

    @staticmethod
    def _detect_format(filepath: Path) -> str:
        """Detect disk image format from extension and file size."""
        ext = filepath.suffix.lower()
        size = filepath.stat().st_size

        # Validate size is a multiple of track size
        if size % 2560 != 0:
            raise ValueError(f"Invalid disk image size: {size} bytes")

        # Check extension first
        if ext == ".ssd":
            return "ssd"
        elif ext == ".dsd":
            return "dsd-interleaved"

        # Fall back to size detection
        tracks = size // 2560
        if tracks in (40, 80):
            return "ssd"
        elif tracks in (80, 160):
            return "dsd-interleaved"
        else:
            raise ValueError(f"Unrecognized disk size: {size} bytes")

    @staticmethod
    def _create_sector_image(disk_image: DiskImage, format: str) -> SectorImage:
        """Create appropriate sector image for format."""
        if format == "ssd":
            return SSDSectorImage(disk_image)
        elif format == "dsd-interleaved":
            # InterleavedDSDSectorImage needs num_tracks
            # Default to 80 tracks (most common)
            size = disk_image.size()
            num_tracks = size // (2 * 10 * 256)  # 2 sides, 10 sectors/track
            return InterleavedDSDSectorImage(disk_image, num_tracks)
        elif format == "dsd-sequential":
            return SequentialDSDSectorImage(disk_image)
        else:
            raise ValueError(f"Unknown format: {format}")

    def __enter__(self) -> "DFSFilesystem":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - flushes changes automatically."""
        if exc_type is None:  # Only flush on success
            self.flush()

    def close(self) -> None:
        """
        Close the disk image, flushing any pending changes.

        After calling close(), the DFSFilesystem instance should not be used.
        Using a context manager (with statement) is preferred.
        """
        self.flush()

    def flush(self) -> None:
        """
        Write any pending changes to disk.

        For file-backed images, this ensures all modifications are persisted.
        For memory-backed images, this writes to the file if filepath is set.

        Raises:
            IOError: If write fails
        """
        if not self._dirty or not self._filepath:
            return

        # If using MemoryDiskImage, write entire image to file
        disk_image = self._sector_image._disk_image
        if isinstance(disk_image, MemoryDiskImage):
            size = disk_image.size()
            data = disk_image.read_bytes(0, size)
            with open(self._filepath, "wb") as f:
                f.write(data)

        # FileDiskImage writes are already persisted
        self._dirty = False

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

        # Read file data sector by sector
        data = bytearray()
        for i in range(entry.sectors_required):
            sector_data = self._sector_image.read_sector(entry.start_sector + i)
            data.extend(sector_data)

        # Return only actual file data (trim padding)
        return bytes(data[: entry.length])

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
            new_title: New disk title (max 12 chars)

        Raises:
            ValueError: If title too long

        Example:
            >>> disk.title = "MY DISK"
        """
        if len(new_title) > 12:
            raise ValueError(f"Title too long (max 12 chars): {new_title}")

        info = self._catalog.read_disk_info()
        info.title = new_title
        self._catalog.write_disk_info(info)
        self._dirty = True

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
        self._dirty = True

    def set_boot_option(self, option: Union[BootOption, int]) -> "DFSFilesystem":
        """
        Set boot option (chainable version).

        Returns self for method chaining.

        Example:
            >>> disk = (DFSFilesystem.create("boot.ssd")
            ...         .set_boot_option(BootOption.EXEC)
            ...         .save_text("$.!BOOT", "*RUN $.MAIN"))
        """
        self.boot_option = option
        return self

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
        free = self.free_sectors

        # Determine format string
        total_sectors = catalog_info.total_sectors
        if total_sectors <= 400:
            format_str = "SSD 40T"
        elif total_sectors <= 800 and isinstance(
            self._sector_image, SSDSectorImage
        ):
            format_str = "SSD 80T"
        elif total_sectors <= 800:
            format_str = "DSD 40T"
        else:
            format_str = "DSD 80T"

        return DiskInfo(
            title=catalog_info.title,
            num_files=catalog_info.num_files,
            total_sectors=catalog_info.total_sectors,
            free_sectors=free,
            boot_option=BootOption(catalog_info.boot_option),
            format=format_str,
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
            f"DFSFilesystem(title='{info.title}', "
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

    @property
    def free_bytes(self) -> int:
        """Get free space in bytes."""
        return self.free_sectors * 256

    def _resolve_filename(self, filename: str) -> str:
        """Resolve filename, adding current directory if needed."""
        if "." not in filename:
            return f"{self._current_directory}.{filename}"
        return filename.upper()

    @classmethod
    def create(
        cls,
        filepath: Union[Path, str],
        *,
        title: str = "",
        num_tracks: int = 40,
        double_sided: bool = False,
        interleaved: bool = True,
    ) -> "DFSFilesystem":
        """
        Create a new formatted disk image (*FORM equivalent).

        Args:
            filepath: Path for new disk image
            title: Disk title (max 12 chars, default: derived from filename)
            num_tracks: Number of tracks (40 or 80, default: 40)
            double_sided: Create double-sided disk (default: False)
            interleaved: Use interleaved format for DSD (default: True)

        Returns:
            DFSFilesystem instance with empty catalog

        Raises:
            ValueError: If parameters are invalid
            FileExistsError: If file already exists

        Example:
            >>> disk = DFSFilesystem.create("new.ssd", title="MY DISK")
            >>> disk.save("$.TEST", b"test data")
            >>> disk.close()
        """
        filepath = Path(filepath)

        if filepath.exists():
            raise FileExistsError(f"File already exists: {filepath}")

        # Validate parameters
        if num_tracks not in (40, 80):
            raise ValueError(f"num_tracks must be 40 or 80, got {num_tracks}")

        if len(title) > 12:
            raise ValueError(f"Title too long (max 12 chars): {title}")

        # Default title from filename
        if not title:
            title = filepath.stem.upper()[:12]

        # Calculate size
        sectors_per_side = num_tracks * 10
        total_sectors = sectors_per_side * (2 if double_sided else 1)
        size = total_sectors * 256

        # Create disk image
        disk_image = MemoryDiskImage(size=size)

        # Create sector image
        if double_sided:
            if interleaved:
                sector_image = InterleavedDSDSectorImage(disk_image, num_tracks)
            else:
                sector_image = SequentialDSDSectorImage(disk_image)
        else:
            sector_image = SSDSectorImage(disk_image)

        # Create and initialize catalog
        catalog = AcornDFSCatalog(sector_image)
        info = CatalogDiskInfo(
            title=title,
            cycle_number=0,
            num_files=0,
            total_sectors=total_sectors,
            boot_option=0,
        )
        catalog.write_disk_info(info)

        instance = cls(catalog, sector_image, filepath)
        instance._dirty = True
        return instance

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
                raise PermissionError(f"Cannot overwrite locked file: {full_name}")
            # Delete existing file first
            self.delete(full_name)

        # Find free space
        start_sector = self._find_free_space(len(data))

        if start_sector is None:
            needed = (len(data) + 255) // 256
            free = self.free_sectors
            raise ValueError(
                f"Cannot save '{full_name}': needs {needed} sectors, "
                f"only {free} free"
            )

        # Write sectors
        sectors_needed = (len(data) + 255) // 256
        padded_data = data + bytes(sectors_needed * 256 - len(data))

        for i in range(sectors_needed):
            sector_data = padded_data[i * 256 : (i + 1) * 256]
            self._sector_image.write_sector(start_sector + i, sector_data)

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
        self._dirty = True

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
        self._dirty = True

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
            raise PermissionError(f"Cannot rename locked file: {old_full}")

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
        self._dirty = True

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
                data = bytearray()
                for i in range(entry.sectors_required):
                    sector_data = self._sector_image.read_sector(
                        entry.start_sector + i
                    )
                    data.extend(sector_data)

                # Write to new location
                for i in range(entry.sectors_required):
                    sector_data = bytes(data[i * 256 : (i + 1) * 256])
                    self._sector_image.write_sector(next_sector + i, sector_data)

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

            self._dirty = True

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
    def create_from_files(
        cls,
        filepath: Union[Path, str],
        files: dict[str, Union[bytes, Path, dict]],
        *,
        title: str = "",
        **create_kwargs,
    ) -> "DFSFilesystem":
        """
        Create a new disk and populate with files in one operation.

        Convenience method for building disk images programmatically.

        Args:
            filepath: Path for new disk image
            files: Dict mapping DFS filenames to data (bytes, Path, or dict with 'data' and metadata)
            title: Disk title
            **create_kwargs: Additional arguments for create()

        Returns:
            DFSFilesystem instance

        Example:
            >>> disk = DFSFilesystem.create_from_files(
            ...     "game.ssd",
            ...     {
            ...         "$.!BOOT": b"*RUN $.MAIN",
            ...         "$.MAIN": Path("build/main.bin"),
            ...         "$.DATA": {"data": b"game data", "load_address": 0x1900}
            ...     },
            ...     title="MY GAME"
            ... )
        """
        disk = cls.create(filepath, title=title, **create_kwargs)

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

        return disk

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

        self._dirty = True

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

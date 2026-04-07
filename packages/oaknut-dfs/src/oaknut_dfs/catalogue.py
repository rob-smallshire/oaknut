"""Abstract base class for disk catalogs and related data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from oaknut_dfs.surface import Surface


@dataclass(frozen=True)
class FileEntry:
    """File entry in a catalog."""

    filename: str  # 7 chars max (without directory)
    directory: str  # Single character (e.g., '$' or 'A')
    locked: bool
    load_address: int  # 18-bit or 32-bit
    exec_address: int
    length: int  # File size in bytes
    start_sector: int  # Where file starts

    @property
    def path(self) -> str:
        """Return path like $.HELLO"""
        return f"{self.directory}.{self.filename}"

    @property
    def sectors_required(self) -> int:
        """Calculate number of sectors needed for file."""
        return (self.length + 255) // 256


@dataclass(frozen=True)
class DiskInfo:
    """Disk catalog metadata."""

    title: str
    cycle_number: int
    num_files: int
    total_sectors: int
    boot_option: int


@dataclass(frozen=True)
class FileInfo:
    """User-facing file information."""

    name: str  # Full name like "$.HELLO"
    directory: str
    filename: str
    locked: bool
    load_address: int
    exec_address: int
    length: int
    start_sector: int
    sectors: int  # Number of sectors occupied


@dataclass(frozen=True)
class ParsedFilename:
    """Validated and parsed filename components."""

    directory: str  # Single character (e.g., '$' or 'A')
    filename: str  # Name part (max 7 chars for Acorn DFS)

    @property
    def path(self) -> str:
        """Return full path like $.HELLO"""
        return f"{self.directory}.{self.filename}"


class Catalogue(ABC):
    """Abstract base class for disk catalogs."""

    # Class constants (must be defined by subclasses)
    CATALOG_START_SECTOR: int
    CATALOG_NUM_SECTORS: int
    CATALOGUE_NAME: str | None = None  # Must be overridden (e.g., "acorn-dfs", "watford-dfs")

    # Registry of catalogue subclasses for format identification
    _registry: dict[str, type['Catalogue']] = {}

    def __init_subclass__(cls, **kwargs):
        """Register catalogue subclass for format identification."""
        super().__init_subclass__(**kwargs)
        # Subclasses must override CATALOGUE_NAME
        assert cls.CATALOGUE_NAME is not None, (
            f"{cls.__name__} must define CATALOGUE_NAME class attribute"
        )
        Catalogue._registry[cls.CATALOGUE_NAME] = cls

    def __init__(self, surface: Surface):
        """Initialize catalog with surface access."""
        self._surface = surface

    @classmethod
    def identify(cls, surface: Surface) -> Optional[type['Catalogue']]:
        """
        Identify which catalogue type this surface uses.

        Tries each registered catalogue type's heuristic check to find
        the best match.

        Args:
            surface: The surface to identify

        Returns:
            Catalogue class that matches, or None if no match found
        """
        for catalogue_cls in cls._registry.values():
            if catalogue_cls.matches(surface):
                return catalogue_cls
        return None

    @classmethod
    @abstractmethod
    def initialise(
        cls,
        surface: Surface,
        total_sectors: int,
        title: str = "",
        boot_option: int = 0,
    ) -> None:
        """Initialise catalogue sectors on a blank surface.

        Writes the catalogue structure (headers, metadata, empty file list)
        to the appropriate sectors, producing a valid empty disc.

        Args:
            surface: The surface to initialise (must be writable).
            total_sectors: Total number of sectors on this side of the disc.
            title: Disc title (default empty).
            boot_option: Boot option 0–3 (default 0).
        """
        pass

    @classmethod
    @abstractmethod
    def matches(cls, surface: Surface) -> bool:
        """
        Check if this catalogue type matches the given surface.

        This is a heuristic check based on catalogue structure, magic bytes,
        validity of metadata, etc.

        Args:
            surface: The surface to check

        Returns:
            True if this surface appears to use this catalogue format
        """
        pass

    @abstractmethod
    def get_disk_info(self) -> DiskInfo:
        """Read disk metadata from catalog."""
        pass

    @abstractmethod
    def list_files(self) -> list[FileEntry]:
        """List all files in catalog."""
        pass

    def find_file(self, filename: str) -> Optional[FileEntry]:
        """Find file by name (case-insensitive)."""
        for entry in self.list_files():
            if entry.path.upper() == filename.upper():
                return entry
        return None

    @abstractmethod
    def add_file_entry(
        self,
        filename: str,
        directory: str,
        load_address: int,
        exec_address: int,
        length: int,
        start_sector: int,
        locked: bool = False,
    ) -> None:
        """Add a new file entry to catalog."""
        pass

    @abstractmethod
    def remove_file_entry(self, filename: str) -> None:
        """Remove file entry from catalog."""
        pass

    @abstractmethod
    def set_title(self, title: str) -> None:
        """Set disk title (max 12 chars)."""
        pass

    @abstractmethod
    def set_boot_option(self, option: int) -> None:
        """Set boot option (0-3)."""
        pass

    @abstractmethod
    def lock_file(self, filename: str) -> None:
        """Lock file to prevent deletion."""
        pass

    @abstractmethod
    def unlock_file(self, filename: str) -> None:
        """Unlock file."""
        pass

    @abstractmethod
    def rename_file(self, old_name: str, new_name: str) -> None:
        """Rename file preserving all metadata and location."""
        pass

    @abstractmethod
    def parse_filename(self, path: str) -> ParsedFilename:
        """
        Parse and validate filename path.

        Args:
            path: Full path (e.g., "$.HELLO") or bare filename (defaults to $ directory)

        Returns:
            ParsedFilename with validated components

        Raises:
            ValueError: If path is invalid for this catalogue type
        """
        pass

    @abstractmethod
    def validate_filename(self, filename: str) -> None:
        """
        Validate filename (without directory).

        Args:
            filename: Filename to validate (e.g., "HELLO")

        Raises:
            ValueError: If filename is invalid (too long, bad encoding, etc.)
        """
        pass

    @abstractmethod
    def validate_directory(self, directory: str) -> None:
        """
        Validate directory character.

        Args:
            directory: Directory character to validate (e.g., '$', 'A')

        Raises:
            ValueError: If directory is invalid
        """
        pass

    @abstractmethod
    def validate_title(self, title: str) -> None:
        """
        Validate disk title.

        Args:
            title: Title to validate

        Raises:
            ValueError: If title is invalid (too long, bad encoding, etc.)
        """
        pass

    def _default_parse_filename(self, path: str, default_directory: str = "$") -> tuple[str, str]:
        """
        Default parsing logic: split on first dot, default to $ directory.

        Subclasses can use this as starting point and then validate.
        """
        if "." in path:
            directory, filename = path.split(".", 1)
            return directory, filename
        return default_directory, path

    @property
    @abstractmethod
    def max_files(self) -> int:
        """Maximum number of files this catalog can hold."""
        pass

    @abstractmethod
    def validate(self) -> list[str]:
        """
        Validate catalogue structure and integrity.

        Checks catalogue-specific constraints like max files, duplicate names,
        overlapping sectors, file bounds, etc.

        Returns:
            List of error messages (empty if valid)
        """
        pass

    @abstractmethod
    def compact(self) -> int:
        """
        Compact catalogue by removing fragmentation.

        Reads file data from sectors, then rewrites files sequentially.
        This consolidates free space at the end. Works at the sector level
        using only the surface abstraction.

        Returns:
            Number of files compacted

        Raises:
            PermissionError: If compaction not allowed (e.g., locked files)
        """
        pass

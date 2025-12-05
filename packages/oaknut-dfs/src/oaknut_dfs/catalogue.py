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


class Catalogue(ABC):
    """Abstract base class for disk catalogs."""

    # Class constants (must be defined by subclasses)
    CATALOG_START_SECTOR: int
    CATALOG_NUM_SECTORS: int

    def __init__(self, surface: Surface):
        """Initialize catalog with surface access."""
        self._surface = surface

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

    @property
    @abstractmethod
    def max_files(self) -> int:
        """Maximum number of files this catalog can hold."""
        pass

# oaknut-dfs Architecture Design

This document describes the layered architecture of the oaknut-dfs Python library for handling Acorn DFS disk images.

## Design Goals

1. **Separation of Concerns** - Each layer has a single, well-defined responsibility
2. **Extensibility** - Support for format variants (Watford DFS, Opus DDOS, etc.) without major refactoring
3. **Testability** - Each layer can be tested independently with mocked dependencies
4. **Usability** - High-level API that mirrors BBC Micro DFS commands while providing Pythonic conveniences

## Layer Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 4: DFS API (dfs_filesystem.py)                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│  • User-facing operations (*CAT, *LOAD, *SAVE, *DELETE, etc.)      │
│  • Context managers and Python conveniences                         │
│  • Format-agnostic (works with any catalog/sector implementation)   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ uses
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 3: Catalog (catalog.py)                                     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│  • Parse and write catalog structures (sectors 0-1)                 │
│  • File entry management (add, remove, find, list)                  │
│  • Catalog validation and integrity checking                        │
│  • Format-specific implementations (AcornCatalog, WatfordCatalog)   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ uses
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 2: Sector Access (sector_image.py)                          │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│  • Logical sector read/write (256-byte sectors)                     │
│  • Physical offset calculation (SSD/DSD, interleaved/sequential)    │
│  • Geometry awareness (tracks, sectors per track)                   │
│  • Abstract base class for format variants                          │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ uses
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: Raw Image (disk_image.py)                                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│  • Raw byte storage abstraction                                     │
│  • No DFS knowledge - pure read/write/resize operations             │
│  • Supports in-memory, file-backed, and mmap implementations        │
└─────────────────────────────────────────────────────────────────────┘
```

## Layer 1: Raw Image (`disk_image.py`)

### Responsibility
Provide a generic byte-level storage abstraction with no knowledge of disk structure or DFS format.

### Key Classes

**`DiskImage` (Abstract Base Class)**
```python
class DiskImage(ABC):
    @abstractmethod
    def read_bytes(self, offset: int, length: int) -> bytes:
        """Read bytes at physical offset."""

    @abstractmethod
    def write_bytes(self, offset: int, data: bytes) -> None:
        """Write bytes at physical offset."""

    @abstractmethod
    def size(self) -> int:
        """Total size in bytes."""

    @abstractmethod
    def resize(self, new_size: int) -> None:
        """Resize the image."""
```

**`MemoryDiskImage`**
- Stores disk image in memory as `bytearray`
- Fast, suitable for small images and testing
- Used when creating new disks or loading from files

**`FileDiskImage`**
- File-backed implementation with buffered I/O
- Suitable for large images or when memory is constrained
- Changes written directly to file

**`MmapDiskImage` (future)**
- Memory-mapped file implementation
- Efficient for large images with random access patterns

### Design Rationale
- **Storage independence:** Allows different backing stores without changing higher layers
- **Testability:** Easy to create in-memory images for unit tests
- **Future-proof:** Can support compressed images, network storage, etc.

## Layer 2: Sector Access (`sector_image.py`)

### Responsibility
Translate logical sector numbers (0-based sequential) into physical byte offsets, handling different disk geometries and interleaving schemes.

### Key Classes

**`SectorImage` (Abstract Base Class)**
```python
class SectorImage(ABC):
    SECTOR_SIZE = 256
    SECTORS_PER_TRACK = 10

    def __init__(self, disk_image: DiskImage):
        self._disk_image = disk_image

    @abstractmethod
    def physical_offset(self, logical_sector: int) -> int:
        """Convert logical sector number to physical byte offset."""

    def read_sector(self, sector: int) -> bytes:
        """Read a complete 256-byte sector."""
        offset = self.physical_offset(sector)
        return self._disk_image.read_bytes(offset, self.SECTOR_SIZE)

    def write_sector(self, sector: int, data: bytes) -> None:
        """Write a complete 256-byte sector."""
        if len(data) != self.SECTOR_SIZE:
            raise ValueError(f"Sector data must be {self.SECTOR_SIZE} bytes")
        offset = self.physical_offset(sector)
        self._disk_image.write_bytes(offset, data)

    @abstractmethod
    def num_sectors(self) -> int:
        """Total number of logical sectors."""
```

**`SSDSectorImage` (Sequential Single-Sided)**
```python
class SSDSectorImage(SectorImage):
    def physical_offset(self, logical_sector: int) -> int:
        return logical_sector * self.SECTOR_SIZE

    def num_sectors(self) -> int:
        return self._disk_image.size() // self.SECTOR_SIZE
```

**`InterleavedDSDSectorImage` (Interleaved Double-Sided)**
```python
class InterleavedDSDSectorImage(SectorImage):
    def physical_offset(self, logical_sector: int) -> int:
        track = logical_sector // self.SECTORS_PER_TRACK
        sector_in_track = logical_sector % self.SECTORS_PER_TRACK
        side = track % 2
        physical_track = track // 2

        return (
            physical_track * self.TRACK_SIZE * 2 +
            side * self.TRACK_SIZE +
            sector_in_track * self.SECTOR_SIZE
        )
```

**`SequentialDSDSectorImage` (Sequential Double-Sided)**
```python
class SequentialDSDSectorImage(SectorImage):
    def physical_offset(self, logical_sector: int) -> int:
        # Simple sequential layout
        return logical_sector * self.SECTOR_SIZE
```

### Design Rationale
- **Extension point for format variants:** Different DFS variants (Watford, Opus) can have different geometries or interleaving
- **Encapsulates complexity:** Physical offset calculation is tricky; this layer hides it
- **Reusable:** Same sector abstraction works for different catalog formats

### Future Extensions

**Watford DFS (62 files, different geometry):**
```python
class WatfordSectorImage(SectorImage):
    # Potentially different sector interleaving or track count
    pass
```

**Opus DDOS (Double density):**
```python
class OpusSectorImage(SectorImage):
    SECTOR_SIZE = 256  # May differ
    SECTORS_PER_TRACK = 18  # Double density
    # Different physical layout
```

## Layer 3: Catalog (`catalog.py`)

### Responsibility
Parse and manage the disk catalog structure (sectors 0-1), providing structured access to file entries and disk metadata.

### Key Classes

**`FileEntry` (Data Class)**
```python
@dataclass
class FileEntry:
    filename: str          # 7 chars max, without directory
    directory: str         # Single character
    locked: bool
    load_address: int      # 18-bit (32-bit with sign extension)
    exec_address: int      # 18-bit (32-bit with sign extension)
    length: int            # 18-bit
    start_sector: int      # 10-bit

    @property
    def full_name(self) -> str:
        return f"{self.directory}.{self.filename.rstrip()}"

    @property
    def sectors_required(self) -> int:
        return (self.length + 255) // 256
```

**`DiskInfo` (Data Class)**
```python
@dataclass
class DiskInfo:
    title: str             # 12 chars max
    cycle_number: int      # Sequence counter
    num_files: int
    total_sectors: int     # 10-bit
    boot_option: int       # 0-3
```

**`Catalog` (Abstract Base Class)**
```python
class Catalog(ABC):
    def __init__(self, sector_image: SectorImage):
        self._sector_image = sector_image

    @abstractmethod
    def read_disk_info(self) -> DiskInfo:
        """Read catalog metadata."""

    @abstractmethod
    def write_disk_info(self, info: DiskInfo) -> None:
        """Write catalog metadata."""

    @abstractmethod
    def list_files(self) -> list[FileEntry]:
        """List all file entries."""

    @abstractmethod
    def find_file(self, filename: str) -> Optional[FileEntry]:
        """Find a file by full name (e.g., '$.HELLO')."""

    @abstractmethod
    def add_file_entry(self, entry: FileEntry) -> None:
        """Add a new file entry to catalog."""

    @abstractmethod
    def remove_file_entry(self, filename: str) -> None:
        """Remove a file entry from catalog."""

    @abstractmethod
    def validate(self) -> list[str]:
        """Validate catalog integrity, return list of errors."""
```

**`AcornDFSCatalog` (Standard Acorn DFS)**
```python
class AcornDFSCatalog(Catalog):
    MAX_FILES = 31
    CATALOG_SECTORS = [0, 1]

    def read_disk_info(self) -> DiskInfo:
        sector0 = self._sector_image.read_sector(0)
        sector1 = self._sector_image.read_sector(1)

        # Parse title (8 bytes from sector0, 4 from sector1)
        title = (sector0[0:8] + sector1[0:4]).decode('ascii').rstrip()

        # Parse metadata from sector1
        cycle = sector1[0x04]
        last_entry = sector1[0x05]
        extra = sector1[0x06]
        sectors_low = sector1[0x07]

        num_files = last_entry // 8
        total_sectors = sectors_low | ((extra & 0x03) << 8)
        boot_option = (extra >> 4) & 0x03

        return DiskInfo(
            title=title,
            cycle_number=cycle,
            num_files=num_files,
            total_sectors=total_sectors,
            boot_option=boot_option
        )

    def list_files(self) -> list[FileEntry]:
        # Implementation reading sectors 0-1 and parsing file entries
        # See dfs-format-spec.md for detailed structure
        pass

    # ... other methods
```

### Design Rationale
- **Format-specific:** Different DFS variants have different catalog structures
- **Structured access:** Converts raw bytes into typed Python objects
- **Validation:** Can check catalog consistency and report errors
- **Immutable reads:** Reading catalog doesn't modify disk state

### Future Extensions

**Watford DFS (62 files, extended catalog):**
```python
class WatfordDFSCatalog(Catalog):
    MAX_FILES = 62  # Double the capacity
    CATALOG_SECTORS = [0, 1, 2]  # Uses 3 sectors instead of 2

    # Different catalog layout and parsing logic
```

## Layer 4: DFS API (`dfs_filesystem.py`)

### Responsibility
Provide a user-friendly, Pythonic API that mirrors BBC Micro DFS commands while adding modern conveniences like context managers and iterators.

### Key Classes

**`DFSImage`**
```python
class DFSImage:
    """High-level DFS filesystem operations."""

    def __init__(self, catalog: Catalog, sector_image: SectorImage):
        self._catalog = catalog
        self._sector_image = sector_image

    @classmethod
    def open(cls, filepath: Path | str) -> "DFSImage":
        """
        Open a disk image file.
        Auto-detects format from extension and size.
        """
        pass

    @classmethod
    def create(cls,
               filepath: Path | str,
               title: str = "NEW DISK",
               num_tracks: int = 40,
               double_sided: bool = False) -> "DFSImage":
        """Create a new formatted disk image."""
        pass

    def __enter__(self) -> "DFSImage":
        """Context manager entry."""
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit (save changes if file-backed)."""
        pass

    # BBC Micro DFS command equivalents

    def cat(self) -> list[FileEntry]:
        """*CAT - List all files."""
        return self._catalog.list_files()

    def info(self) -> DiskInfo:
        """*INFO - Get disk information."""
        return self._catalog.read_disk_info()

    def load(self, filename: str) -> bytes:
        """
        *LOAD - Read file data.

        Args:
            filename: Full filename (e.g., '$.HELLO')

        Returns:
            File data as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        entry = self._catalog.find_file(filename)
        if entry is None:
            raise FileNotFoundError(f"File not found: {filename}")

        # Read file data sector by sector
        data = bytearray()
        for i in range(entry.sectors_required):
            sector_data = self._sector_image.read_sector(
                entry.start_sector + i
            )
            data.extend(sector_data)

        return bytes(data[:entry.length])

    def save(self,
             filename: str,
             data: bytes,
             load_address: int = 0,
             exec_address: int = 0,
             locked: bool = False) -> None:
        """
        *SAVE - Write file to disk.

        Args:
            filename: Full filename (e.g., '$.HELLO')
            data: File data
            load_address: Load address (default: 0)
            exec_address: Execution address (default: 0)
            locked: Lock file after saving (default: False)

        Raises:
            ValueError: If disk is full or filename invalid
        """
        # Find free space, write sectors, update catalog
        pass

    def delete(self, filename: str) -> None:
        """
        *DELETE - Remove file from disk.

        Args:
            filename: Full filename (e.g., '$.HELLO')

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file is locked
        """
        pass

    def rename(self, old_name: str, new_name: str) -> None:
        """*RENAME - Rename a file."""
        pass

    def access(self, filename: str, locked: Optional[bool] = None) -> None:
        """*ACCESS - Change file lock status."""
        pass

    def title(self, new_title: str) -> None:
        """*TITLE - Change disk title."""
        pass

    def opt(self, boot_option: int) -> None:
        """*OPT 4,n - Set boot option (0-3)."""
        pass

    # Python conveniences

    def __iter__(self):
        """Iterate over files."""
        return iter(self.cat())

    def __contains__(self, filename: str) -> bool:
        """Check if file exists."""
        return self._catalog.find_file(filename) is not None

    def free_sectors(self) -> int:
        """Calculate number of free sectors."""
        pass

    def compact(self) -> None:
        """Defragment disk (move files to eliminate gaps)."""
        pass
```

### Design Rationale
- **Familiar API:** Methods named after BBC Micro DFS commands
- **Pythonic:** Also provides Python idioms (context managers, iterators, `in` operator)
- **Format-agnostic:** Works with any catalog/sector implementation
- **Convenience:** Higher-level operations built on lower layers

### Usage Examples

```python
# Open existing disk
with DFSImage.open("games.ssd") as disk:
    print(f"Disk: {disk.info().title}")

    # List files
    for file in disk.cat():
        print(f"  {file.full_name:12} {file.length:6} bytes")

    # Load a file
    data = disk.load("$.ELITE")

    # Save a file
    disk.save("$.HELLO", b"PRINT 'Hello!'",
              load_address=0x1900, exec_address=0x1900)

# Create new disk
disk = DFSImage.create("new.ssd", title="MY DISK", num_tracks=40)
disk.save("$.TEST", b"Test data")
disk.save("new.ssd")  # Explicit save for non-context usage
```

## Cross-Layer Design Principles

### 1. Dependency Direction
Dependencies flow downward only:
- API → Catalog → Sector → Raw Image
- Higher layers never exposed to lower layer implementation details

### 2. Abstraction Boundaries
Each layer has clear responsibilities:
- **Raw Image:** Bytes at offsets
- **Sector:** 256-byte blocks with logical numbering
- **Catalog:** File entries and metadata
- **API:** User operations and conveniences

### 3. Extension Points

**Adding Watford DFS support:**
```python
# Layer 2: New sector implementation (if needed)
class WatfordSectorImage(SectorImage):
    pass

# Layer 3: New catalog implementation
class WatfordDFSCatalog(Catalog):
    MAX_FILES = 62
    # Different catalog parsing

# Layer 4: No changes needed!
# Same DFSImage works with WatfordDFSCatalog
```

### 4. Testing Strategy

**Unit tests per layer:**
- **Raw Image:** Test byte read/write, resize
- **Sector:** Test offset calculations with mock disk image
- **Catalog:** Test parsing with mock sector data
- **API:** Test operations with mock catalog

**Integration tests:**
- Load real SSD/DSD files
- Verify round-trip (read → modify → write → read)
- Test with reference implementations (BeebEm, b-em)

## File Organization

```
src/oaknut_dfs/
├── __init__.py              # Public API exports
├── disk_image.py            # Layer 1: Raw image implementations
├── sector_image.py          # Layer 2: Sector access
├── catalog.py               # Layer 3: Catalog structures
├── dfs_filesystem.py        # Layer 4: DFS API
├── exceptions.py            # Custom exceptions
└── constants.py             # Shared constants

tests/
├── test_disk_image.py       # Layer 1 tests
├── test_sector_image.py     # Layer 2 tests
├── test_catalog.py          # Layer 3 tests
├── test_dfs_filesystem.py   # Layer 4 tests
└── test_integration.py      # End-to-end tests
```

## Summary

This four-layer architecture provides:

1. **Clear separation of concerns** - Each layer has one job
2. **Extensibility** - Easy to add Watford DFS, Opus DDOS, etc.
3. **Testability** - Each layer tested independently
4. **Usability** - High-level API hides complexity
5. **Maintainability** - Changes localized to specific layers

The design prioritizes **extensibility at the Sector and Catalog layers** while keeping the Raw Image and API layers format-agnostic.

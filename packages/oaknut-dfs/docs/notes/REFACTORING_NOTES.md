# API Refactoring Summary

## Changes Made

### 1. Introduced `DiskFormat` Class

The `DiskFormat` dataclass bundles together the sector image class and catalog class that define a disk format:

```python
@dataclass
class DiskFormat:
    name: str
    sector_image_class: Type[SectorImage]
    catalog_class: Type[Catalog]
```

### 2. Standard Format Constants

Pre-defined format constants for common Acorn DFS formats:

- `ACORN_SSD` - Single-sided, sequential
- `ACORN_DSD` - Double-sided, interleaved (standard)
- `ACORN_DSD_SEQUENTIAL` - Double-sided, sequential

### 3. Simplified `create()` API

**Old API:**
```python
DFSImage.create("disk.ssd", num_tracks=40)
DFSImage.create("disk.dsd", num_tracks=40, double_sided=True, interleaved=True)
```

**New API:**
```python
DFSImage.create("disk.ssd", num_tracks_per_side=40)  # Auto-detects ACORN_SSD
DFSImage.create("disk.dsd", num_tracks_per_side=40)  # Auto-detects ACORN_DSD
DFSImage.create("disk.dsd", format=ACORN_DSD_SEQUENTIAL)  # Explicit format
```

**Benefits:**
- `num_tracks_per_side` removes ambiguity (always 40 or 80)
- No boolean flags for `double_sided` and `interleaved`
- Extensible for new formats without changing `DFSImage`

### 4. Sector Image Factory Methods

Each sector image class now has a `create_formatted()` class method:

```python
class SSDSectorImage(SectorImage):
    @classmethod
    def create_formatted(cls, num_tracks_per_side: int = 40) -> "SSDSectorImage":
        # Creates properly-sized disk image
        # Returns initialized SectorImage instance
```

This delegates geometry calculations to the appropriate layer.

### 5. Title Validation in Catalog

Title length validation moved from `DFSImage` to `AcornDFSCatalog`:

```python
class AcornDFSCatalog(Catalog):
    MAX_TITLE_LENGTH = 12

    def write_disk_info(self, info: DiskInfo) -> None:
        if len(info.title) > self.MAX_TITLE_LENGTH:
            raise ValueError(f"Title too long (max {self.MAX_TITLE_LENGTH} chars)")
        # ... write catalog
```

This allows different catalog types to have different title length constraints.

## Adding New Formats (e.g., Watford DDFS)

To add support for a new disk format:

### 1. Create Sector Image Class (if needed)

```python
class WatfordDSDSectorImage(SectorImage):
    """Watford DDFS sector layout."""

    @classmethod
    def create_formatted(cls, num_tracks_per_side: int = 40) -> "WatfordDSDSectorImage":
        # Watford-specific geometry
        total_tracks = num_tracks_per_side * 2
        size = total_tracks * cls.SECTORS_PER_TRACK * cls.SECTOR_SIZE
        disk_image = MemoryDiskImage(size=size)
        return cls(disk_image, num_tracks_per_side)

    def physical_offset(self, logical_sector: int) -> int:
        # Watford-specific sector interleaving
        pass
```

### 2. Create Catalog Class

```python
class WatfordDFSCatalog(Catalog):
    """Watford DDFS catalog (62 files, sectors 0-2)."""

    MAX_FILES = 62
    MAX_TITLE_LENGTH = 12  # Or different if Watford allows longer

    def read_disk_info(self) -> DiskInfo:
        # Parse Watford catalog structure (sectors 0-2)
        pass

    def write_disk_info(self, info: DiskInfo) -> None:
        if len(info.title) > self.MAX_TITLE_LENGTH:
            raise ValueError(f"Title too long (max {self.MAX_TITLE_LENGTH} chars)")
        # Write Watford catalog structure
        pass

    # Implement other Catalog methods...
```

### 3. Create Format Constant

```python
WATFORD_DDFS = DiskFormat(
    name="Watford DDFS",
    sector_image_class=WatfordDSDSectorImage,
    catalog_class=WatfordDFSCatalog,
)
```

### 4. Use It

```python
from oaknut_dfs import DFSImage, WATFORD_DDFS

# Create Watford DDFS disk
disk = DFSImage.create("watford.dsd", format=WATFORD_DDFS, num_tracks_per_side=40)
disk.save("$.FILE", b"data")
disk.close()

# Open Watford DDFS disk (needs format detection enhancement)
disk = DFSImage.open("watford.dsd", format="watford-ddfs")  # Would need string detection
```

### 5. Export in Package

```python
# In __init__.py
from oaknut_dfs.dfs_filesystem import WATFORD_DDFS

__all__ = [
    # ...existing exports...
    "WATFORD_DDFS",
]
```

## Architecture Benefits

1. **Separation of Concerns**: Each layer knows only what it needs to know
2. **No Coupling**: `DFSImage` doesn't know about specific format details
3. **Extensibility**: Add new formats without modifying existing code
4. **Type Safety**: IDE autocomplete works with format constants
5. **Validation at Right Layer**: Catalog validates its own constraints
6. **Delegated Calculations**: Geometry calculations in sector image classes

## Testing

All 535 existing tests pass with the new API.

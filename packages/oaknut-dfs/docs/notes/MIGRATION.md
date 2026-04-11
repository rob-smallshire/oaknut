# Migration Guide: oaknut-dfs Refactoring

## Summary of Changes

The architecture has been refactored from 4 layers to 3 layers, replacing the DiskImage abstraction with direct buffer access.

### Architecture

**Old (4 layers):**
```
DFSImage → Catalog → SectorImage → DiskImage (FileDiskImage/MemoryDiskImage)
```

**New (3 layers):**
```
DFSImage → Catalog → SectorImage → buffer (mmap/bytearray/memoryview)
```

### Key API Changes

#### 1. Opening Disks - Now Context Managers

**Old:**
```python
disk = DFSImage.open("games.ssd")
data = disk.load("$.ELITE")
# No cleanup needed (but no mmap either)
```

**New:**
```python
with DFSImage.open("games.ssd") as disk:
    data = disk.load("$.ELITE")
# mmap automatically closed
```

#### 2. Creating Disks - Now Context Managers

**Old:**
```python
disk = DFSImage.create("new.ssd", title="MY DISK")
disk.save("$.TEST", b"data")
```

**New:**
```python
with DFSImage.create("new.ssd", title="MY DISK") as disk:
    disk.save("$.TEST", b"data")
```

#### 3. Constructor Changed - Takes Buffer

**Old:**
```python
disk_img = FileDiskImage("disk.ssd")
sector_img = SSDSectorImage(disk_img)
catalog = AcornDFSCatalog(sector_img)
disk = DFSImage(catalog, sector_img, filepath)
```

**New:**
```python
# Direct buffer construction
buffer = bytearray(204800)
disk = DFSImage(buffer, format="ssd")

# Or from file
with open("disk.ssd", "r+b") as f:
    mm = mmap.mmap(f.fileno(), 0)
    disk = DFSImage(mm, format="ssd")
```

#### 4. New: from_bytes() Method

**New convenience method:**
```python
with open("disk.ssd", "rb") as f:
    data = f.read()

disk = DFSImage.from_bytes(data)
disk.save("$.TEST", b"test")
modified = bytes(disk._buffer)
```

#### 5. Format Constants Renamed

**Old:**
```python
from oaknut_dfs import ACORN_SSD, ACORN_DSD
disk = DFSImage.create("new.ssd", format=ACORN_SSD)
```

**New:**
```python
from oaknut_dfs import FORMAT_SSD, FORMAT_DSD_INTERLEAVED
disk = DFSImage.create("new.ssd", format=FORMAT_SSD)
# But usually you can use format="auto" (the default)
```

#### 6. create_from_files() Now Context Manager

**Old:**
```python
disk = DFSImage.create_from_files("game.ssd", {
    "$.BOOT": b"*RUN $.MAIN",
    "$.MAIN": Path("main.bin"),
})
```

**New:**
```python
with DFSImage.create_from_files("game.ssd", {
    "$.BOOT": b"*RUN $.MAIN",
    "$.MAIN": Path("main.bin"),
}) as disk:
    print(f"Created with {len(disk.files)} files")
```

### New Capabilities

#### 1. Memory-mapped File Access

```python
# Automatic mmap via context manager
with DFSImage.open("large.ssd") as disk:
    # Efficient - no full file read into memory
    data = disk.load("$.FILE")
```

#### 2. Direct Buffer Access

```python
# In-memory disk
buffer = bytearray(204800)
disk = DFSImage(buffer, format="ssd")
disk.save("$.TEST", b"data")

# Get modified bytes
modified = bytes(disk._buffer)
```

#### 3. Sub-region Support (for MMB)

```python
# Access disk within MMB container
with open("container.mmb", "r+b") as f:
    mm = mmap.mmap(f.fileno(), 0)
    # Extract disk 5
    disk_view = memoryview(mm)[disk_num * 204800:(disk_num + 1) * 204800]
    disk = DFSImage(disk_view, format="ssd")
    # Writes go directly to MMB file!
```

### Internal Changes

#### SectorImage Changes

**Old:**
```python
class SectorImage:
    def __init__(self, disk_image: DiskImage):
        self._disk_image = disk_image

    def read_sector(self, sector: int) -> bytes:
        # Returns bytes
```

**New:**
```python
class SectorImage:
    def __init__(self, buffer):
        self._buffer = memoryview(buffer)

    def get_sector(self, sector: int) -> memoryview:
        # Zero-copy view

    def read_sector(self, sector: int) -> bytes:
        # Compatibility method, copies

    def get_sectors(self, start: int, count: int) -> SectorsView:
        # Returns SectorsView (smart about contiguous/non-contiguous)
```

#### New: SectorsView Class

Presents multiple sectors as a single buffer-like object:
```python
# Handles both contiguous and non-contiguous sectors
sectors = sector_img.get_sectors(10, 5)
if sectors.contiguous:
    print("Zero-copy access!")
data = sectors[:100]  # Works like bytes
```

### Testing Migration

**Old test pattern:**
```python
def test_something():
    disk_img = MemoryDiskImage(size=204800)
    sector_img = SSDSectorImage(disk_img)
    catalog = AcornDFSCatalog(sector_img)
    dfs = DFSImage(catalog, sector_img)
```

**New test pattern:**
```python
def test_something():
    buffer = bytearray(204800)
    dfs = DFSImage(buffer, format="ssd")
    # or
    dfs = DFSImage.from_bytes(b"\x00" * 204800, format="ssd")
```

### CLI Migration

**Old:**
```python
disk = DFSImage.open(args.image_file)
# ... use disk ...
```

**New:**
```python
with DFSImage.open(args.image_file) as disk:
    # ... use disk ...
```

## Benefits of New Architecture

1. **Simpler**: 3 layers instead of 4
2. **More efficient**: mmap for large files, zero-copy where possible
3. **More flexible**: Works with any buffer (mmap, bytearray, memoryview slice)
4. **Better resource management**: Context managers ensure cleanup
5. **MMB-ready**: Can operate on memoryview slices
6. **More Pythonic**: Follows Python conventions for file-like objects

## Files Removed

- `disk_image.py` - No longer needed
- `DiskImage`, `FileDiskImage`, `MemoryDiskImage` classes

## Files Added

- `sectors_view.py` - New SectorsView class with buffer protocol

## Files Modified

- `sector_image.py` - Takes buffers instead of DiskImage
- `dfs_filesystem.py` - New constructor, context managers
- `__init__.py` - Updated exports

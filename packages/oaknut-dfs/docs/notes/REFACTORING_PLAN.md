# DFS Filesystem Refactoring Plan

## Overview
Refactoring oaknut-dfs to use memoryview/mmap instead of custom DiskImage layer.

## Goals
1. Remove DiskImage layer entirely - use buffers directly
2. Support memory-mapped files for efficient file I/O
3. Enable direct access to sub-regions (for future MMB support)
4. Use SectorsView for transparent contiguous/non-contiguous sector handling

## Architecture Changes

### Old Stack (4 layers)
```
DFSFilesystem → Catalog → SectorImage → DiskImage
                                        ↓
                                   FileDiskImage / MemoryDiskImage
```

### New Stack (3 layers)
```
DFSImage → Catalog → SectorImage
                     ↓
                  buffer (mmap, bytearray, memoryview)
```

## API Changes

### DFSImage Constructor
**Old:**
```python
def __init__(self, catalog, sector_image, filepath)
```

**New:**
```python
def __init__(self, buffer, *, format="auto", side=0)
# buffer can be: mmap, bytearray, memoryview, bytes
# Creates sector_image and catalog internally
```

### DFSImage.open() - Context Manager
**Old:**
```python
disk = DFSImage.open("disk.ssd")  # Returns DFSImage directly
disk.load("$.FILE")
disk.close()  # No-op
```

**New:**
```python
with DFSImage.open("disk.ssd") as disk:  # Context manager with mmap
    disk.load("$.FILE")
# mmap automatically closed
```

### DFSImage.create() - Context Manager
**Old:**
```python
disk = DFSImage.create("new.ssd", title="MY DISK")
disk.save("$.FILE", data)
disk.close()  # No-op
```

**New:**
```python
with DFSImage.create("new.ssd", title="MY DISK") as disk:
    disk.save("$.FILE", data)
# mmap automatically closed
```

### New: DFSImage.from_bytes()
```python
# For in-memory or testing
disk = DFSImage.from_bytes(data, format="ssd")
disk.save("$.TEST", b"test")
modified = bytes(disk._buffer)
```

### New: Direct buffer construction
```python
# From MMB container (future)
with open("container.mmb", "r+b") as f:
    mm = mmap.mmap(f.fileno(), 0)
    disk_view = memoryview(mm)[disk_num * 204800:(disk_num + 1) * 204800]
    disk = DFSImage(disk_view, format="ssd")
    # Changes write directly to MMB via mmap!
```

## Implementation Steps

1. ✅ Create SectorsView class with buffer protocol
2. ✅ Refactor SectorImage to use buffers
3. ✅ Add read_sector() compatibility method
4. ⏳ Update DFSImage:
   - New __init__(buffer, format, side)
   - Context manager open() using @contextmanager
   - Context manager create() using @contextmanager
   - Add from_bytes() class method
   - Update _create_sector_image() to not use DiskImage
5. ⏳ Update __init__.py exports
6. ⏳ Remove disk_image.py
7. ⏳ Update all tests
8. ⏳ Update CLI

## Breaking Changes

### For Users
1. **Context managers required**: `open()` and `create()` now return context managers
   ```python
   # Old:
   disk = DFSImage.open("disk.ssd")

   # New:
   with DFSImage.open("disk.ssd") as disk:
       ...
   ```

2. **Constructor signature changed**: Direct construction now takes buffer
   ```python
   # Old: construct from layers
   disk_img = FileDiskImage("disk.ssd")
   sector_img = SSDSectorImage(disk_img)
   catalog = AcornDFSCatalog(sector_img)
   disk = DFSImage(catalog, sector_img, "disk.ssd")

   # New: construct from buffer
   with open("disk.ssd", "r+b") as f:
       mm = mmap.mmap(f.fileno(), 0)
       disk = DFSImage(mm, format="ssd")
   ```

### For Tests
- Tests using MemoryDiskImage → use bytearray directly
- Tests using FileDiskImage → use mmap or context managers
- No more manual layer construction needed

## Compatibility Notes

### What Stays the Same
- All high-level DFSImage methods: load(), save(), delete(), etc.
- Catalog interface unchanged
- SectorImage read_sector()/write_sector() unchanged (compatibility methods)
- File format detection logic unchanged

### What Changes
- DiskImage classes removed
- SectorImage takes buffer instead of DiskImage
- New methods: get_sector(), get_sectors() for zero-copy access
- open()/create() are context managers
- Constructor takes buffer not layers

## Testing Strategy

1. Update test utilities to use bytearray
2. Update integration tests to use context managers
3. Add tests for:
   - SectorsView with contiguous sectors
   - SectorsView with non-contiguous sectors
   - Buffer protocol support
   - mmap-backed disks
   - Sliced memoryviews

## Migration Path

### For oaknut-dfs internal code
1. Update CLI to use context managers
2. Update examples in docstrings
3. Update CLAUDE.md documentation

### For external users (if any)
1. Document breaking changes in release notes
2. Provide migration examples
3. Consider deprecation warnings for old patterns (if needed)

## Future Enhancements Enabled

1. **MMB support**: Pass memoryview slice of MMB container
2. **Network backed disks**: Custom buffer class wrapping network I/O
3. **Compressed disks**: Decompress to bytearray on-demand
4. **Copy-on-write**: Use memoryview of immutable bytes for read-only

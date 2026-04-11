# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

oaknut-dfs is a Python library for handling Acorn DFS (Disc Filing System) disk images in SSD and DSD formats, used by BBC Micro and Acorn Electron computers. The library provides both a Python API and CLI for disk operations.

## Development Commands

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_dfs_filesystem.py

# Run tests with coverage
pytest --cov=oaknut_dfs

# Run a single test
pytest tests/test_catalog.py::test_read_disk_info
```

### Development Setup
```bash
# Install for development (if not already installed)
uv sync

# Run linter
ruff check src/ tests/
```

### CLI Usage
```bash
# The CLI tool is installed as oaknut-dfs
oaknut-dfs cat disk.ssd
oaknut-dfs info disk.ssd
oaknut-dfs load disk.ssd '$.HELLO' output.bin
```

## Architecture

The codebase uses a **3-layer architecture** that separates concerns and enables extensibility for DFS variants (Watford DFS, Opus DDOS, etc.):

### Layer 1: Sector Access (`sector_image.py`)
- Operates directly on buffers (mmap, bytearray, memoryview)
- Converts logical sector numbers to physical byte offsets
- Handles disk geometry and interleaving schemes
- **Key classes:**
  - `SectorImage` (ABC): Takes buffer and sectors_per_track parameter
  - `SSDSectorImage`: Single-sided sequential layout
  - `InterleavedDSDSectorImage`: Double-sided with track interleaving
  - `SequentialDSDSectorImage`: Double-sided sequential layout
  - `SSDSideSectorImage`: Wrapper for accessing one side with uniform API
  - `DSDSideSectorImage`: Wrapper for accessing one side of DSD
  - `SectorsView`: Buffer-protocol object presenting multiple sectors as contiguous
- Constants: SECTOR_SIZE=256, ACORN_DFS_SECTORS_PER_TRACK=10
- **sectors_per_track is parameterized** to support formats like Watford DDFS (18 sectors/track)

### Layer 2: Catalog Management (`catalog.py`)
- Parses and manages catalog structure in sectors 0-1
- **Key classes:**
  - `Catalog` (ABC): read_disk_info(), list_files(), find_file(), add_file_entry(), remove_file_entry()
  - `AcornDFSCatalog`: Standard Acorn DFS (31 files max)
  - `FileEntry`: Dataclass with filename, directory, locked, load_address, exec_address, length, start_sector
  - `DiskInfo`: Dataclass with title, cycle_number, num_files, total_sectors, boot_option
- Uses Acorn character encoding (custom codec registered in `acorn_encoding.py`)

### Layer 3: DFS API (`dfs_filesystem.py`)
- User-facing Pythonic API mirroring BBC Micro DFS star commands
- **Key class:** `DFSFilesystem`
- **Methods mirror DFS commands:**
  - `load(filename)` → *LOAD
  - `save(filename, data, ...)` → *SAVE
  - `delete(filename)` → *DELETE
  - `rename(old, new)` → *RENAME
  - `lock(filename)`, `unlock(filename)` → *ACCESS
  - Properties: `title`, `boot_option`, `files`, `info`, `free_sectors`
- Python conveniences: context managers, iteration, `in` operator

### Acorn Character Encoding (`acorn_encoding.py`)
- Custom Python codec for BBC Micro character set
- Key differences from ASCII: 0x60=£, 0x7C=¦
- Registered codec name: 'acorn'
- Usage: `text.encode('acorn')`, `bytes.decode('acorn')`

### CLI Layer (`cli.py`)
- Click-based command-line interface
- Commands: cat, info, load, save, delete, rename, lock, unlock, create, title, opt, compact, validate, export-all, import-inf, dump, copy

## Key Design Patterns

### Dependency Flow
Dependencies flow downward only:
- API → Catalog → Sector → Raw Image
- Each layer only knows about the layer directly below it

### Format Detection
- File extensions: .ssd (single-sided), .dsd (double-sided)
- Size validation: Must be multiple of 2560 bytes (track size)
- Auto-detection in `DFSFilesystem.open()` via `_detect_format()` and `_create_sector_image()`

### File Operations
1. **Reading files:** Get FileEntry from catalog → read sectors via sector_image → return trimmed data
2. **Writing files:** Find free space → write padded sectors → add catalog entry → increment cycle number
3. **Deleting files:** Check not locked → remove from catalog → rebuild catalog sectors

### Catalog Structure
- Sectors 0-1 hold catalog (512 bytes total)
- Sector 0: Title (8 bytes) + file entries (8 bytes each)
- Sector 1: Title continuation (4 bytes) + metadata + file entry details (8 bytes each)
- Max 31 files in standard Acorn DFS
- Each file entry split across both sectors with bit-packed high bits

## Testing Notes

- Test files are in `tests/` directory
- Each layer has dedicated test files matching the architecture
- Integration tests in `test_dfs_integration.py`
- Tests use pytest fixtures for setup/teardown
- In-memory disk images used extensively for fast testing

## Important Implementation Details

### Address Handling
- Load/exec addresses are 18-bit with potential sign extension to 32-bit
- I/O processor addresses (0xFFFFxxxx range) require special handling
- High bits packed into "extra byte" in catalog entries

### Sector Allocation
- Sectors 0-1 reserved for catalog
- Files stored contiguously in sectors
- Free space calculated by building used sector map
- Compaction moves files to eliminate gaps

### DSD Interleaving
The InterleavedDSDSectorImage uses complex offset calculation:
- Logical sectors numbered sequentially: 0, 1, 2, ...
- Physical layout alternates sides per track
- Formula in `physical_offset()` at src/oaknut_dfs/sector_image.py:190

### Dirty Tracking
- `_dirty` flag tracks when changes need flushing
- Context manager auto-flushes on successful exit
- FileDiskImage writes immediately; MemoryDiskImage buffers until flush

## Variable Naming Conventions

The codebase follows these suffix conventions:
- `_filename`: Just the name part (e.g., "HELLO")
- `_filepath`: Full path to file (e.g., Path("/path/to/disk.ssd"))
- `_dirpath`: Directory path
- `_dirname`: Directory name
- Avoid ambiguous `_file` or `_dir` suffixes

## Advanced Usage

### Mixed-Format DSD Images

While rare, it's technically possible to have a DSD image where the two sides use different formats (e.g., side 0 is Acorn DFS with 10 sectors/track, side 1 is Watford DDFS with 18 sectors/track). The BBC Micro treats each side as an independent drive (drives 0/2 or 1/3).

The high-level `DFSImage` API assumes uniform sides (the normal case). For mixed-format images, users can create custom `SectorImage` subclasses that understand the specific physical layout:

```python
# Custom sector image for mixed-format DSD
class MixedFormatDSDSide(SectorImage):
    def __init__(self, buffer, side, side0_spt, side1_spt, tracks_per_side):
        # Custom logic for physical_offset() that knows about
        # different sectors_per_track values for each side
        pass

# Use at low level
with open("mixed.dsd", "r+b") as f:
    mm = mmap.mmap(f.fileno(), 0)
    side0_img = MixedFormatDSDSide(mm, side=0, side0_spt=10, side1_spt=18, tracks_per_side=40)
    side0_catalog = AcornDFSCatalog(side0_img)
    # Manually construct DFSImage
    ...
```

### Direct Buffer Manipulation

For maximum flexibility (e.g., working with MMB containers), construct `DFSImage` directly from buffers:

```python
# From memoryview slice (e.g., MMB container)
with open("container.mmb", "r+b") as f:
    mm = mmap.mmap(f.fileno(), 0)
    disk_offset = disk_number * 204800
    disk_view = memoryview(mm)[disk_offset:disk_offset + 204800]
    disk = DFSImage(disk_view, format="ssd")
    # Changes write directly to MMB file via mmap
```

## Common Tasks

### Adding a new DFS variant (e.g., Watford DDFS)
Watford DDFS uses 18 sectors per track instead of Acorn's 10.

1. **Sector image**: Usually no new class needed - use existing classes with `sectors_per_track=18`
   ```python
   watford_img = InterleavedDSDSectorImage(buffer, tracks_per_side=40, sectors_per_track=18)
   ```

2. **Catalog**: Create `WatfordDDFSCatalog(Catalog)` in catalog.py
   - Watford DDFS has extended catalog (62 files instead of 31)
   - Different catalog layout and metadata

3. **High-level API**: Add format constants and detection in dfs_filesystem.py
   ```python
   FORMAT_WATFORD_DDFS = "watford-ddfs"
   ```

4. **Format detection**: Update `_detect_format_from_size()` and `_create_sector_image()`
   - Watford DDFS: 40 tracks × 2 sides × 18 sectors × 256 bytes = 368,640 bytes

### Modifying catalog structure parsing
- Edit `AcornDFSCatalog.read_disk_info()` or `list_files()` in catalog.py
- Update corresponding write methods to maintain consistency
- Refer to docs/dfs-format-spec.md for catalog byte layout
- Remember to use 'acorn' encoding for text fields

### Adding new CLI commands
1. Add @cli.command() decorated function in cli.py
2. Use existing DFSFilesystem methods from dfs_filesystem.py
3. Follow pattern of error handling with sys.exit(1) on errors
4. Use click.echo() for output

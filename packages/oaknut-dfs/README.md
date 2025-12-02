# oaknut-dfs

Python library for handling Acorn DFS (Disc Filing System) disk images in SSD and DSD formats.

## Installation

Using uv:

```bash
uv pip install oaknut-dfs
```

For development:

```bash
uv pip install -e ".[dev]"
```

## Overview

This package provides:

- Python API mirroring the original BBC Micro Disc Filing System commands
- CLI for disk operations
- Support for both single-sided (SSD) and double-sided (DSD) disk images
- Proper DSD handling with independent catalogs per side

## Quick Start

### Python API

```python
from oaknut_dfs import DFSImage

# Open single-sided disk
with DFSImage.open("disk.ssd") as disk:
    print(disk.title)
    print(disk.files)
    data = disk.load("$.HELLO")

# Open double-sided disk (side 0)
with DFSImage.open("disk.dsd", side=0) as disk:
    disk.save("$.FILE", b"data")

# Open double-sided disk (side 1)
with DFSImage.open("disk.dsd", side=1) as disk:
    disk.save("$.OTHER", b"data")
```

### CLI

```bash
# List catalog of single-sided disk
oaknut-dfs cat disk.ssd

# List catalog of double-sided disk (side 0)
oaknut-dfs cat disk.dsd --side=0

# List catalog of double-sided disk (side 1)
oaknut-dfs cat disk.dsd --side=1

# Load file from side 1 of DSD
oaknut-dfs load disk.dsd '$.FILE' --side=1
```

## Double-Sided Disk Support

DSD (double-sided) disk images contain two independent sides, each with its own catalog:

- **Side 0**: First side (400 sectors for 40T, 800 sectors for 80T)
- **Side 1**: Second side (400 sectors for 40T, 800 sectors for 80T)

Each side has:
- Independent catalog in sectors 0-1
- Independent disk title and boot option
- Completely separate files (files on one side are not visible from the other)

This mirrors the BBC Micro DFS behavior, where double-sided disks were accessed as separate drives using `*DRIVE 0` and `*DRIVE 2`.

### Python API

```python
# Create double-sided disk (initializes both sides)
disk = DFSImage.create("disk.dsd", num_tracks=40, double_sided=True)
disk.close()

# Work with side 0
disk0 = DFSImage.open("disk.dsd", side=0)
disk0.title = "SIDE ZERO"
disk0.save("$.FILE0", b"side 0 data")
disk0.close()

# Work with side 1
disk1 = DFSImage.open("disk.dsd", side=1)
disk1.title = "SIDE ONE"
disk1.save("$.FILE1", b"side 1 data")
disk1.close()

# Sides are independent
disk0 = DFSImage.open("disk.dsd", side=0)
assert disk0.exists("$.FILE0")
assert not disk0.exists("$.FILE1")  # Side 1 file not visible
```

### CLI

All commands that access disk images support the `--side` option:

```bash
# View catalog of each side
oaknut-dfs cat disk.dsd --side=0
oaknut-dfs cat disk.dsd --side=1

# Get disk info
oaknut-dfs info disk.dsd --side=0
oaknut-dfs info disk.dsd --side=1

# File operations on specific side
oaknut-dfs load disk.dsd '$.FILE' --side=1
oaknut-dfs save disk.dsd file.bin '$.NEWFILE' --side=1
oaknut-dfs delete disk.dsd '$.OLDFILE' --side=0

# Set different titles per side
oaknut-dfs title disk.dsd "SIDE ZERO" --side=0
oaknut-dfs title disk.dsd "SIDE ONE" --side=1

# Export files from specific side
oaknut-dfs export-all disk.dsd output_dir/ --side=1
```

The `--side` option defaults to 0 for backward compatibility. SSD (single-sided) images only support `--side=0`.

## Development

Run tests:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=oaknut_dfs
```

## Architecture

The library uses a layered architecture:

1. **Layer 1: Raw Image Storage** (`disk_image.py`) - Byte-level storage
2. **Layer 2: Sector Access** (`sector_image.py`) - Logical sector addressing
3. **Layer 3: Catalog Management** (`catalog.py`) - DFS catalog structure
4. **Layer 4: DFS API** (`dfs_filesystem.py`) - High-level operations

For DSD files, `DSDSideSectorImage` wraps the interleaved physical layout to provide per-side logical addressing.

## License

MIT

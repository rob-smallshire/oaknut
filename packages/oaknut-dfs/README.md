# oaknut-dfs

Python library for handling Acorn DFS (Disc Filing System) disc images in SSD and DSD formats.

## Installation

As a library dependency in your project:

```bash
uv add oaknut-dfs
```

As a CLI tool:

```bash
uv tool install oaknut-dfs
```

For development:

```bash
uv sync
```

## Overview

This package provides:

- Python API mirroring the original BBC Micro Disc Filing System commands
- CLI for disc operations
- Support for both single-sided (SSD) and double-sided (DSD) disc images
- Proper DSD handling with independent catalogs per side

## Quick Start

### Python API

```python
from oaknut_dfs import DFSImage

# Open single-sided disc
with DFSImage.open("disc.ssd") as disk:
    print(disk.title)
    print(disk.files)
    data = disk.load("$.HELLO")

# Open double-sided disc (side 0)
with DFSImage.open("disc.dsd", side=0) as disk:
    disk.save("$.FILE", b"data")

# Open double-sided disc (side 1)
with DFSImage.open("disc.dsd", side=1) as disk:
    disk.save("$.OTHER", b"data")
```

### CLI

```bash
# List catalog of single-sided disc
oaknut-dfs cat disc.ssd

# List catalog of double-sided disc (side 0)
oaknut-dfs cat disc.dsd --side=0

# List catalog of double-sided disc (side 1)
oaknut-dfs cat disc.dsd --side=1

# Load file from side 1 of DSD
oaknut-dfs load disc.dsd '$.FILE' --side=1
```

## Double-Sided Disc Support

DSD (double-sided) disc images contain two independent sides, each with its own catalog:

- **Side 0**: First side (400 sectors for 40T, 800 sectors for 80T)
- **Side 1**: Second side (400 sectors for 40T, 800 sectors for 80T)

Each side has:
- Independent catalog in sectors 0-1
- Independent disc title and boot option
- Completely separate files (files on one side are not visible from the other)

This mirrors the BBC Micro DFS behavior, where double-sided discs were accessed as separate drives using `*DRIVE 0` and `*DRIVE 2`.

### Python API

```python
# Create double-sided disc (initializes both sides)
disk = DFSImage.create("disc.dsd", num_tracks=40, double_sided=True)
disk.close()

# Work with side 0
disk0 = DFSImage.open("disc.dsd", side=0)
disk0.title = "SIDE ZERO"
disk0.save("$.FILE0", b"side 0 data")
disk0.close()

# Work with side 1
disk1 = DFSImage.open("disc.dsd", side=1)
disk1.title = "SIDE ONE"
disk1.save("$.FILE1", b"side 1 data")
disk1.close()

# Sides are independent
disk0 = DFSImage.open("disc.dsd", side=0)
assert disk0.exists("$.FILE0")
assert not disk0.exists("$.FILE1")  # Side 1 file not visible
```

### CLI

All commands that access disc images support the `--side` option:

```bash
# View catalog of each side
oaknut-dfs cat disc.dsd --side=0
oaknut-dfs cat disc.dsd --side=1

# Get disc info
oaknut-dfs info disc.dsd --side=0
oaknut-dfs info disc.dsd --side=1

# File operations on specific side
oaknut-dfs load disc.dsd '$.FILE' --side=1
oaknut-dfs save disc.dsd file.bin '$.NEWFILE' --side=1
oaknut-dfs delete disc.dsd '$.OLDFILE' --side=0

# Set different titles per side
oaknut-dfs title disc.dsd "SIDE ZERO" --side=0
oaknut-dfs title disc.dsd "SIDE ONE" --side=1

# Export files from specific side
oaknut-dfs export-all disc.dsd output_dir/ --side=1
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

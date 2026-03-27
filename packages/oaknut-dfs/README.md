# oaknut-dfs

[![PyPI version](https://img.shields.io/pypi/v/oaknut-dfs)](https://pypi.org/project/oaknut-dfs/)
[![CI](https://github.com/rob-smallshire/oaknut-dfs/actions/workflows/tests.yml/badge.svg)](https://github.com/rob-smallshire/oaknut-dfs/actions/workflows/tests.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-dfs)](https://pypi.org/project/oaknut-dfs/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-dfs)](https://github.com/rob-smallshire/oaknut-dfs/blob/master/LICENSE)

A Python library for reading and writing
[Acorn DFS](https://en.wikipedia.org/wiki/Disc_Filing_System) (Disc Filing
System) disc images in SSD and DSD formats, as used by the
[BBC Micro](https://en.wikipedia.org/wiki/BBC_Micro) and
[Acorn Electron](https://en.wikipedia.org/wiki/Acorn_Electron).

## The problem

Software for the BBC Micro and related Acorn 8-bit computers is commonly
distributed as disc images in SSD (single-sided) and DSD (double-sided)
formats. These images contain a DFS catalogue structure that encodes
filenames, load addresses, execution addresses, and file attributes in a
format specific to the Acorn Disc Filing System.

Working with these images programmatically --- extracting files, inspecting
metadata, creating new images, or modifying existing ones --- requires
understanding the low-level catalogue format and sector layout. oaknut-dfs
provides a Pythonic API that handles these details, letting you work with
DFS disc images using familiar Python patterns.

## Supported formats

- **Acorn DFS**: 40-track and 80-track, single-sided (SSD) and double-sided (DSD)
- **Watford DFS**: Extended catalogue supporting up to 62 files (format constants defined)
- **DSD interleaving**: Both interleaved and sequential double-sided layouts
- **Acorn character encoding**: Custom codec for the BBC Micro character set (`£`, `¦`)

## Prerequisites

oaknut-dfs is a standard Python package and can be installed with any Python
package manager, including `pip`. The instructions below use
[`uv`](https://docs.astral.sh/uv/), which handles Python installation,
dependency resolution, and virtual environments automatically.

### Installing uv

**macOS (Homebrew):**

```
brew install uv
```

**Linux / macOS (standalone installer):**

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**

```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

See the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/)
for other methods including pip, pipx, Cargo, Conda, Winget, and Scoop.

## Installation

### As a library dependency

```
uv add oaknut-dfs
```

or with pip:

```
pip install oaknut-dfs
```

### For development

```
uv sync
```

## Usage

### Opening a disc image

```python
from oaknut_dfs import DFS, ACORN_DFS_80T_SINGLE_SIDED

with DFS.from_file("Zalaga.ssd", ACORN_DFS_80T_SINGLE_SIDED) as dfs:
    print(dfs.title)   # 'ZALAG-L'
    print(len(dfs))    # 4 files
```

### Reading the catalogue

```python
for entry in dfs.files:
    lock = "L" if entry.locked else " "
    print(
        f"{lock} {entry.path:10s}"
        f"  load={entry.load_address:08X}"
        f"  exec={entry.exec_address:08X}"
        f"  length={entry.length:5d}"
    )
# L $.ZALAGA?   load=00003000  exec=00004522  length=11557
# L $.ZALAGA    load=000023EE  exec=00002400  length= 2816
# L $.ZALAG-L   load=00001900  exec=00001900  length= 3328
# L $.!BOOT     load=00000000  exec=00000000  length=   48
```

### File information

```python
info = dfs.get_file_info("$.ZALAGA?")
print(info.name)              # '$.ZALAGA?'
print(hex(info.load_address)) # 0x3000
print(hex(info.exec_address)) # 0x4522
print(info.length)            # 11557
print(info.locked)            # True
print(info.start_sector)      # 27
print(info.sectors)           # 46
```

### Loading a file

```python
# Get the catalogue entry for the main game binary
info = dfs.get_file_info("$.ZALAGA")
print(hex(info.load_address))  # 0x23ee — where to load in memory
print(hex(info.exec_address))  # 0x2400 — entry point for execution
print(info.length)             # 2816 bytes

# Load the file data
data = dfs.load("$.ZALAGA")
print(len(data))               # 2816
```

### Disc information

```python
print(dfs.info)
# {
#     'title': 'ZALAG-L\x00\x00\x00\x00\x00',
#     'num_files': 4,
#     'total_sectors': 800,
#     'free_sectors': 727,
#     'boot_option': 3,
# }
```

### Pythonic interface

```python
# Check if a file exists
print("$.!BOOT" in dfs)    # True
print("$.MISSING" in dfs)  # False

# Number of files
print(len(dfs))             # 4

# Iterate over filenames
for entry in dfs:
    print(entry.path)
# $.ZALAGA?
# $.ZALAGA
# $.ZALAG-L
# $.!BOOT
```

### Creating and writing disc images

```python
from oaknut_dfs import ACORN_DFS_40T_SINGLE_SIDED

# Create an empty 40-track single-sided disc in memory
buffer = bytearray(102400)  # 40 tracks * 10 sectors * 256 bytes
# ... initialise catalogue sectors ...

dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

# Save files with load and execution addresses
dfs.save("$.HELLO", b"Hello, World!", load_address=0x1200, exec_address=0x1200)
dfs.save("$.README", b"oaknut-dfs demo disc")

# Load a file back
data = dfs.load("$.HELLO")
print(data)   # b'Hello, World!'

print(repr(dfs))   # DFS(title='DEMO', files=2, free_sectors=396)
```

### Double-sided discs (DSD)

```python
from oaknut_dfs import ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED

# DSD images contain two independent sides, each with its own catalogue.
# This mirrors the BBC Micro, where double-sided discs were accessed as
# separate drives using *DRIVE 0 and *DRIVE 2.

buffer = bytearray(204800)  # 40-track double-sided
# ... initialise catalogue sectors for both sides ...

# Access each side independently
dfs0 = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=0)
dfs1 = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=1)

# Each side has its own title, files, and catalogue
print(dfs0.title)   # 'SIDE ZERO'
print(dfs1.title)   # 'SIDE ONE'

# Files on one side are not visible from the other
print("$.FILE0" in dfs0)   # True
print("$.FILE0" in dfs1)   # False
```

## Development

After cloning, install the pre-commit hooks:

```
uv run --group dev pre-commit install
```

### Running the tests

```
uv run --group test pytest tests/ -v
```

## Architecture

The library uses a layered architecture with dependencies flowing downward:

1. **Sector access** (`surface.py`, `sectors_view.py`) --- operates on buffers
   to convert logical sector numbers to physical byte offsets. Handles disc
   geometry and interleaving schemes.

2. **Catalogue management** (`catalogue.py`, `acorn_dfs_catalogue.py`,
   `watford_dfs_catalogue.py`) --- parses and manages the DFS catalogue
   structure in sectors 0--1. Supports Acorn DFS (31 files) and Watford DFS
   (62 files).

3. **DFS API** (`dfs.py`) --- user-facing Pythonic interface mirroring BBC
   Micro DFS star commands. Supports file operations, disc metadata, iteration,
   and the `in` operator.

## References

### Format specifications

- [Acorn DFS disc format](https://beebwiki.mdfs.net/Acorn_DFS_disc_format) ---
  BeebWiki specification for the Acorn DFS catalogue layout.
- [Disc Filing System](https://en.wikipedia.org/wiki/Disc_Filing_System) ---
  Wikipedia overview of DFS and its variants.
- [INF file format](https://beebwiki.mdfs.net/INF_file_format) ---
  BeebWiki specification for the `.inf` sidecar metadata format.

### Related tools and projects

- [oaknut-zip](https://github.com/rob-smallshire/oaknut-zip) ---
  Sister project for extracting ZIP files containing Acorn metadata.

### Forum discussions

- [Stardot forum: DFS format](https://stardot.org.uk/forums/viewtopic.php?t=4714) ---
  Community discussion of DFS disc image formats and variants.

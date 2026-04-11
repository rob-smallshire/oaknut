# oaknut-dfs

[![PyPI version](https://img.shields.io/pypi/v/oaknut-dfs.svg)](https://pypi.org/project/oaknut-dfs/)
[![CI](https://github.com/rob-smallshire/oaknut-dfs/actions/workflows/tests.yml/badge.svg)](https://github.com/rob-smallshire/oaknut-dfs/actions/workflows/tests.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-dfs.svg)](https://pypi.org/project/oaknut-dfs/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-dfs.svg)](https://github.com/rob-smallshire/oaknut-dfs/blob/master/LICENSE)

A Python library for reading, writing, and creating
[Acorn DFS](https://en.wikipedia.org/wiki/Disc_Filing_System) and
[ADFS](https://en.wikipedia.org/wiki/Advanced_Disc_Filing_System)
disc images, as used by the
[BBC Micro](https://en.wikipedia.org/wiki/BBC_Micro),
[Acorn Electron](https://en.wikipedia.org/wiki/Acorn_Electron),
and [BBC Master](https://en.wikipedia.org/wiki/BBC_Master).

With oaknut-dfs you can open DFS floppy images (SSD/DSD), ADFS floppy
images (ADF/ADL), and ADFS hard disc images (DAT/DSC) to browse
directories, read and write files, inspect metadata, and create new
formatted disc images --- all from Python, with a pathlib-inspired API.

## Supported formats

### DFS (Disc Filing System)

- **Acorn DFS**: 40-track and 80-track, single-sided (SSD) and double-sided (DSD)
- **Watford DFS**: Extended catalogue supporting up to 62 files
- **DSD interleaving**: Both interleaved and sequential double-sided layouts

### ADFS (Advanced Disc Filing System)

- **ADFS S/M/L**: Single- and double-sided floppy images (ADF/ADL)
- **ADFS hard disc**: SCSI hard disc images (DAT + DSC sidecar pairs)
- **Hierarchical directories**: Full directory tree navigation with pathlib-inspired API
- **Old map format**: Free space map parsing and validation

### Common

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

### DFS disc images

#### Opening and reading files

```python
from oaknut_dfs import DFS, ACORN_DFS_80T_SINGLE_SIDED

with DFS.from_file("Zalaga.ssd", ACORN_DFS_80T_SINGLE_SIDED) as dfs:
    print(dfs.title)   # 'ZALAG-L'

    # Navigate with pathlib-inspired API
    for entry in dfs.root / "$":
        s = entry.stat()
        print(f"{entry.name:10s}  {s.length:6d}  load={s.load_address:08X}")

    # Read file data
    data = (dfs.root / "$" / "ZALAGA").read_bytes()
```

#### Creating a new DFS disc

```python
from oaknut_dfs import DFS, ACORN_DFS_80T_SINGLE_SIDED

with DFS.create_file("demo.ssd", ACORN_DFS_80T_SINGLE_SIDED, title="DEMO") as dfs:
    dfs.save("$.HELLO", b"Hello, World!", load_address=0x1900)
    dfs.save("$.README", b"oaknut-dfs demo disc")
```

#### Double-sided discs (DSD)

DSD images contain two independent sides, each with its own catalogue.
This mirrors the BBC Micro, where double-sided discs were accessed as
separate drives using `*DRIVE 0` and `*DRIVE 2`.

```python
from oaknut_dfs import DFS, ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED

with DFS.from_file("game.dsd", ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED) as side0:
    print(side0.title)

with DFS.from_file("game.dsd", ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, side=1) as side1:
    print(side1.title)
```

#### Walking the disc

DFS directories (`$`, `A`--`Z`) appear as children of a virtual root:

```python
with DFS.from_file("disc.ssd", ACORN_DFS_80T_SINGLE_SIDED) as dfs:
    for dirpath, dirnames, filenames in dfs.root.walk():
        for name in filenames:
            print(dirpath / name)
```

### ADFS floppy disc images

#### Opening and navigating

ADFS supports hierarchical directories. The format is auto-detected from
the image size:

```python
from oaknut_dfs import ADFS

with ADFS.from_file("MasterWelcome.adl") as adfs:
    print(adfs.title)   # '80T Welcome & Utils'

    # Navigate with / operator
    for entry in adfs.root / "LIBRARY":
        print(entry.name, entry.stat().length)

    # Read a file
    data = (adfs.root / "HELP" / "aform").read_bytes()
```

#### Walking the directory tree

```python
with ADFS.from_file("disc.adl") as adfs:
    for dirpath, dirnames, filenames in adfs.root.walk():
        for name in filenames:
            print(dirpath / name)
```

#### Creating a new ADFS floppy

```python
from oaknut_dfs import ADFS, ADFS_L

with ADFS.create_file("blank.adl", ADFS_L, title="My Disc") as adfs:
    pass  # empty formatted disc ready for use
```

Available floppy formats: `ADFS_S` (160KB), `ADFS_M` (320KB), `ADFS_L` (640KB).

### ADFS hard disc images

Hard disc images consist of a `.dat` file (raw sector data) and a `.dsc`
sidecar file (SCSI disc geometry). Pass either file to `from_file` ---
the companion is located automatically.

#### Opening a hard disc image

```python
from oaknut_dfs import ADFS

with ADFS.from_file("scsi0.dat") as adfs:
    print(adfs.title)
    print(f"{adfs.total_size // 1024}KB, {adfs.free_space // 1024}KB free")

    for dirpath, dirnames, filenames in adfs.root.walk():
        for name in filenames:
            p = dirpath / name
            print(f"{p}  {p.stat().length}")
```

#### Creating a new hard disc image

Specify a capacity and the geometry is chosen automatically (4 heads,
33 sectors/track --- the Acorn convention):

```python
from oaknut_dfs import ADFS

# Create a 20MB hard disc image
with ADFS.create_file("scsi0.dat", capacity_bytes=20 * 1024 * 1024, title="Data") as adfs:
    pass  # creates both scsi0.dat and scsi0.dsc
```

For explicit geometry control:

```python
with ADFS.create_file("scsi0.dat", cylinders=306, heads=4) as adfs:
    pass
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

1. **Sector access** (`surface.py`, `sectors_view.py`, `unified_disc.py`) ---
   operates on buffers to convert logical sector numbers to physical byte
   offsets. Handles disc geometry, interleaving schemes, and multi-surface
   aggregation.

2. **Catalogue and directory management** --- two parallel implementations:
   - **DFS** (`catalogue.py`, `acorn_dfs_catalogue.py`,
     `watford_dfs_catalogue.py`) --- flat catalogue in sectors 0--1. Supports
     Acorn DFS (31 files) and Watford DFS (62 files).
   - **ADFS** (`adfs_directory.py`, `adfs_free_space_map.py`) --- hierarchical
     directories stored as disc objects, with an explicit free space map.

3. **Filesystem API** --- user-facing interfaces with pathlib-inspired navigation:
   - **DFS** (`dfs.py`) --- `DFS`, `DFSPath`, `DFSStat`
   - **ADFS** (`adfs.py`) --- `ADFS`, `ADFSPath`, `ADFSStat`

## References

### Format specifications

- [Acorn DFS disc format](https://beebwiki.mdfs.net/Acorn_DFS_disc_format) ---
  BeebWiki specification for the Acorn DFS catalogue layout.
- [Disc Filing System](https://en.wikipedia.org/wiki/Disc_Filing_System) ---
  Wikipedia overview of DFS and its variants.
- [Advanced Disc Filing System](https://en.wikipedia.org/wiki/Advanced_Disc_Filing_System) ---
  Wikipedia overview of ADFS and its evolution.
- [Guide to Disc Formats](https://github.com/geraldholdsworth/DiscImageManager) ---
  Gerald Holdsworth's detailed technical reference for DFS, ADFS, and other formats.
- [INF file format](https://beebwiki.mdfs.net/INF_file_format) ---
  BeebWiki specification for the `.inf` sidecar metadata format.

### Related tools and projects

- [oaknut-zip](https://github.com/rob-smallshire/oaknut-zip) ---
  Sister project for extracting ZIP files containing Acorn metadata.

### Forum discussions

- [Stardot forum: DFS format](https://stardot.org.uk/forums/viewtopic.php?t=4714) ---
  Community discussion of DFS disc image formats and variants.

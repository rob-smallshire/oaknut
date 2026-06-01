# oaknut-dfs

[![PyPI version](https://img.shields.io/pypi/v/oaknut-dfs)](https://pypi.org/project/oaknut-dfs/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-dfs)](https://pypi.org/project/oaknut-dfs/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-dfs)](https://github.com/rob-smallshire/oaknut/blob/master/packages/oaknut-dfs/LICENSE)

A Python library for reading, writing, and creating
[Acorn DFS](https://en.wikipedia.org/wiki/Disc_Filing_System) floppy disc
images, as used by the
[BBC Micro](https://en.wikipedia.org/wiki/BBC_Micro).

With oaknut-dfs you can open DFS floppy images (SSD/DSD) to browse the
catalogue, read and write files, inspect metadata, and create new
formatted discs — all from Python, with a pathlib-inspired API.

> **Looking for ADFS?** The hierarchical Advanced Disc Filing System lives
> in the sibling [`oaknut-adfs`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-adfs)
> package (`from oaknut.adfs import ADFS`). DFS and ADFS are independent
> filing systems and independent packages. For a unified command-line tool
> across DFS, ADFS, AFS, ROMFS and ZIP, see
> [`oaknut-disc`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-disc).

Part of the [oaknut](https://github.com/rob-smallshire/oaknut) monorepo.

## Supported formats

- **Acorn DFS** — 40-track and 80-track, single-sided (SSD) and
  double-sided (DSD)
- **Watford DFS** — extended catalogue supporting up to 62 files
- **DSD interleaving** — both interleaved and sequential double-sided
  layouts

Acorn load/exec addresses, the lock bit, and the BBC Micro character set
(the `acorn` text codec, `£`, `¦`) are handled through the shared
[`oaknut-file`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-file)
metadata layer.

## Installation

```sh
uv add oaknut-dfs      # or: pip install oaknut-dfs
```

oaknut-dfs is a standard Python package installable with any package
manager; the examples use [`uv`](https://docs.astral.sh/uv/).

## Usage

### Opening and reading files

The disc format is auto-detected from the file extension and size; pass
a format explicitly only to override detection.

```python
from oaknut.dfs import DFS

with DFS.from_file("Zalaga.ssd") as dfs:
    print(dfs.title)   # 'ZALAG-L'

    # Navigate with a pathlib-inspired API.
    for entry in dfs.root / "$":
        s = entry.stat()
        print(f"{entry.name:10s}  {s.length:6d}  load={s.load_address:08X}")

    # Read file data.
    data = (dfs.root / "$" / "ZALAGA").read_bytes()
```

### Creating a new disc

```python
from oaknut.dfs import DFS, ACORN_DFS_80T_SINGLE_SIDED

with DFS.create_file("demo.ssd", ACORN_DFS_80T_SINGLE_SIDED, title="DEMO") as dfs:
    (dfs.root / "$.HELLO").write_bytes(b"Hello, World!", load_address=0x1900)
    (dfs.root / "$.README").write_bytes(b"oaknut-dfs demo disc")
```

### Double-sided discs (DSD)

A DSD image holds two independent sides, each with its own catalogue —
mirroring the BBC Micro, where the sides were accessed as separate drives
(`*DRIVE 0` and `*DRIVE 2`). Select a side with the `side=` argument.

```python
from oaknut.dfs import DFS

with DFS.from_file("game.dsd") as side0:
    print(side0.title)

with DFS.from_file("game.dsd", side=1) as side2:
    print(side2.title)
```

### Walking the disc

DFS directories (`$`, `A`–`Z`) appear as children of a virtual root:

```python
with DFS.from_file("disc.ssd") as dfs:
    for dirpath, dirnames, filenames in dfs.root.walk():
        for name in filenames:
            print(dirpath / name)
```

## Development

The package is developed in the [oaknut](https://github.com/rob-smallshire/oaknut)
workspace. From the repository root:

```sh
uv sync                                 # install all workspace members editable
uv run pytest packages/oaknut-dfs/tests # this package's tests
uv run ruff check                       # lint
```

## Architecture

A layered design, dependencies flowing strictly downward (every module
imports only from the layer below):

```
DFS (dfs.py)                       user-facing DFS / DFSPath / DFSStat
  ↓
CataloguedSurface (catalogued_surface.py)
  ↓
Catalogue ABC (catalogue.py)   ←   AcornDFSCatalogue / WatfordDFSCatalogue
  ↓
Surface / SectorsView          (from oaknut-discimage)
```

- `dfs.py` — user-facing `DFS`, `DFSPath`, `DFSStat`; methods mirror the
  DFS star commands (`load`, `save`, `delete`, `rename`, `lock`, …).
- `catalogue.py` — the catalogue ABC (`Catalogue`, `FileEntry`,
  `DiscInfo`): 31-file cap, single-character directories, 7-char names.
- `acorn_dfs_catalogue.py` / `watford_dfs_catalogue.py` — the Acorn
  (sectors 0–1, 31 files) and Watford (sectors 0–3, 62 files) catalogues.
- `catalogued_surface.py` — pairs a `Surface` with a `Catalogue`.
- `formats.py` — DFS and Watford disc-format constants.

Sector-level access (`Surface`, `SectorsView`, `UnifiedDisc`) lives in
[`oaknut-discimage`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-discimage);
metadata and the `acorn` codec in `oaknut-file`; BBC BASIC
(de)tokenisation (for `DFSPath.read_basic` / `write_basic`) in
`oaknut-basic`.

## References

- [Acorn DFS disc format](https://beebwiki.mdfs.net/Acorn_DFS_disc_format) —
  BeebWiki specification for the catalogue layout.
- [Disc Filing System](https://en.wikipedia.org/wiki/Disc_Filing_System) —
  Wikipedia overview of DFS and its variants.
- [DiscImageManager](https://github.com/geraldholdsworth/DiscImageManager) —
  Gerald Holdsworth's reference for DFS and other Acorn formats.
- [INF file format](https://beebwiki.mdfs.net/INF_file_format) —
  the `.inf` sidecar metadata format.

## License

MIT — see [LICENSE](LICENSE).

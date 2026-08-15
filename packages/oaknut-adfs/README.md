# oaknut-adfs

[![PyPI version](https://img.shields.io/pypi/v/oaknut-adfs)](https://pypi.org/project/oaknut-adfs/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-adfs)](https://pypi.org/project/oaknut-adfs/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-adfs)](https://github.com/rob-smallshire/oaknut/blob/master/packages/oaknut-adfs/LICENSE)

A Python library for reading, writing, and creating
[Acorn ADFS](https://en.wikipedia.org/wiki/Advanced_Disc_Filing_System)
(Advanced Disc Filing System) disc images — the hierarchical filing system
used by the [BBC Master](https://en.wikipedia.org/wiki/BBC_Master),
[Acorn Archimedes](https://en.wikipedia.org/wiki/Acorn_Archimedes), and
[RISC OS](https://en.wikipedia.org/wiki/RISC_OS).

oaknut-adfs opens ADFS floppy and hard-disc images to browse the directory
tree, read and write files and directories, inspect and edit RISC OS
metadata (filetypes, datestamps, access), and create new formatted discs —
from Python, with a `pathlib`-inspired API.

> **Looking for DFS?** The flat-catalogue Disc Filing System of the BBC
> Micro is a separate filing system in the sibling
> [`oaknut-dfs`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-dfs)
> package (`from oaknut.dfs import DFS`). For a unified command-line tool
> across DFS, ADFS, AFS, ROMFS and ZIP, see
> [`oaknut-disc`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-disc).

Part of the [oaknut](https://github.com/rob-smallshire/oaknut) monorepo.

## Supported formats

ADFS evolved across three machine generations. oaknut-adfs reads, writes,
and creates every standard floppy format and the FileCore hard-disc layout:

| Format | Map | Directory | Capacity | Sector | Zones | Notes |
|--------|-----|-----------|----------|--------|-------|-------|
| **S**  | Old | Old       | 160 KB   | 256 B  | —     | 40-track single-sided; ADFS on the BBC B / Electron |
| **M**  | Old | Old       | 320 KB   | 256 B  | —     | 80-track single-sided |
| **L**  | Old | Old       | 640 KB   | 256 B  | —     | 80-track double-sided |
| **D**  | Old | New       | 800 KB   | 1024 B | —     | Arthur / the BBC Master 512 |
| **E**  | New | New       | 800 KB   | 1024 B | 1     | double density; RISC OS |
| **E+** | New | Big       | 800 KB   | 1024 B | 1     | RISC OS 4 — long filenames |
| **F**  | New | New       | 1600 KB  | 1024 B | 4     | high density; RISC OS |
| **F+** | New | Big       | 1600 KB  | 1024 B | 4     | RISC OS 4 — long filenames |
| **G**  | New | New       | 3200 KB  | 1024 B | 8     | extra-high density; rarely used |
| **G+** | New | Big       | 3200 KB  | 1024 B | 8     | RISC OS 4 — long filenames; rarely used |
| **Hard disc** | New | New / Big | multi-megabyte | 256 / 512 B | many | Archimedes / RISC OS FileCore |

The **map** and **directory** are independent axes; the format letter is
shorthand for a particular pairing.

### Allocation maps

- **Old map** — a free-space map in sectors 0–1, listing free fragments as
  `(start, length)` pairs, guarded by two additive checksums. Files occupy
  contiguous sectors. Used by S, M, L and D.
- **New map** (FileCore) — a fragmented allocation scheme. A *disc record*
  at offset `0x04` describes the geometry; a zoned allocation bitmap tracks
  variable-length fragments addressed by a fragment id plus a sector offset.
  This is what lifts the size ceiling of the old map and allows the multi-zone
  F and G formats and large hard discs. Used by E, F, G and their `+`
  variants.

### Directory formats

- **Old directory** (`Hugo`) — a fixed 1280-byte block, up to 47 entries,
  10-character names. Used by S, M and L.
- **New directory** (`Hugo` / `Nick`) — a fixed 2048-byte block, 10-character
  names, carrying the 32-bit RISC OS load/exec fields. Used by D, E, F and G.
- **Big directory** (`SBPr` / `oven`) — a variable-size block with a packed
  name heap, supporting filenames of up to 255 characters. Used by the `+`
  formats (E+, F+, G+).

### Hard-disc images

New-map hard discs are read, written, and created in both common on-disc
layouts:

- **`.hdf`** — RPCEmu / Arculator IDE images, where FileCore numbers sectors
  from `low_sector`, placing disc address 0 at a `0x200` offset. Detected and
  handled by content.
- **`.dat` / `.dsc`** — a raw image with a 22-byte SCSI geometry sidecar; the
  New-map geometry is read from the disc record, so the sidecar is optional.

## Metadata

RISC OS is a 32-bit system, and its per-file metadata lives in the load and
execution address fields:

- **Filetypes and datestamps.** When the top 12 bits of the load address are
  `&FFF`, the field encodes a 12-bit filetype and a 40-bit datestamp
  (centiseconds since 1900) rather than genuine addresses. oaknut-adfs stores
  both the raw fields and, through the
  [`oaknut.filesystem`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-filesystem)
  capability layer, the decoded filetype and datestamp.
- **Access bits.** Owner and public read/write, plus the lock (`L`) bit, via
  the shared
  [`oaknut-file`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-file)
  `Access` type.

Content-based identification (via `oaknut.filesystem`) recognises every map
and directory combination above, so a disc need not be labelled by extension.

## Installation

```sh
uv add oaknut-adfs        # or: pip install oaknut-adfs
```

oaknut-adfs works with any [PEP 517](https://peps.python.org/pep-0517/) build
front-end and package manager; the examples use
[`uv`](https://docs.astral.sh/uv/).

## Usage

### Opening and reading

The format is auto-detected from the image content (and, where content is
ambiguous, the file extension). Pass a format only to override detection.

```python
from oaknut.adfs import ADFS

with ADFS.from_file("RISCOS.adf") as adfs:
    print(adfs.title)

    # Navigate with a pathlib-inspired API; "$" is the root.
    for entry in (adfs.root / "$").iterdir():
        s = entry.stat()
        print(f"{entry.name:12s} {s.length:7d}  load={s.load_address:08X}")

    data = (adfs.root / "$" / "!Boot").read_bytes()
```

`from_file` opens the image read/write when host permissions allow; pass
`read_only=True` to guarantee a shared image cannot be modified.

### Creating a disc

Every floppy format has a module constant. Pass it to `create_file`:

```python
from oaknut.adfs import ADFS, ADFS_E, ADFS_F_PLUS

# An 800 KB New-map E disc.
with ADFS.create_file("disc.adf", ADFS_E, title="RISCOS") as adfs:
    (adfs.root / "$.ReadMe").write_bytes(
        b"oaknut-adfs demo", load_address=0xFFFFFF00, exec_address=0x00000000
    )
    (adfs.root / "$.Apps").mkdir()

# A 1600 KB F+ disc, whose Big directories allow long filenames.
with ADFS.create_file("big.adf", ADFS_F_PLUS, title="Extended") as adfs:
    (adfs.root / "$.AVeryLongFileNameIndeed").write_bytes(b"...")
```

### Hard-disc images

```python
from oaknut.adfs import ADFS

# Size a New-map hard disc from a capacity; big_directories=True selects
# the Big directory (E+/F+) layout.
adfs = ADFS.create_new_map_hard_disc("40MB", title="IDEDisc", big_directories=True)
```

### Validating structure

`validate()` walks the whole disc — map, zone checks, and directory tree —
and returns a list of structural errors (empty when the disc is sound):

```python
with ADFS.from_file("disc.adf") as adfs:
    errors = adfs.validate()
    assert errors == []
```

## Development

The package is developed in the
[oaknut](https://github.com/rob-smallshire/oaknut) workspace. From the
repository root:

```sh
uv sync                                  # install all workspace members editable
uv run pytest packages/oaknut-adfs/tests # this package's tests
uv run ruff check                        # lint
```

## Architecture

A layered design, dependencies flowing strictly downward:

```
ADFS (adfs.py)                     user-facing ADFS / ADFSPath / ADFSStat
  ↓
directory.py  ←→  free_space_map.py  ←→  new_map.py
  (Old/New/Big dirs)  (old map)          (FileCore new map)
  ↓
UnifiedDisc / Surface / SectorsView   (from oaknut-discimage)
```

- `adfs.py` — the user-facing `ADFS`, `ADFSPath`, `ADFSStat`; format
  detection, the format constants, and disc creation.
- `directory.py` — the Old, New, and Big directory formats (parse, serialise,
  and their respective check-byte algorithms).
- `free_space_map.py` — the old-map free-space map and its checksums.
- `new_map.py` — the FileCore disc record, zoned allocation bitmap, fragment
  allocation and sharing, and blank-image formatting.
- `filesystem.py` — the `oaknut.filesystem` adapter: content identification,
  the mount, and the Filetyped / Datestamped capabilities.

Sector-level access (`Surface`, `SectorsView`, `UnifiedDisc`) lives in
[`oaknut-discimage`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-discimage);
metadata and the `acorn` codec in
[`oaknut-file`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-file);
BBC BASIC (de)tokenisation in
[`oaknut-basic`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-basic).

`oaknut-adfs` and `oaknut-dfs` are independent siblings: `from oaknut.dfs
import ADFS` does not work — ADFS lives in `oaknut.adfs`.

## Further reading

- [Advanced Disc Filing System](https://en.wikipedia.org/wiki/Advanced_Disc_Filing_System) —
  Wikipedia overview of ADFS and its formats.
- [FileCore](https://gitlab.riscosopen.org/RiscOS/Sources/FileSys/FileCore) —
  the RISC OS Open source for the New-map filing core (Apache 2.0).
- [Guide to Acorn Disc Images](https://www.geraldholdsworth.co.uk/documents/DiscImage.pdf) —
  Gerald Holdsworth's specification of the ADFS map and directory formats.
- [INF file format](https://beebwiki.mdfs.net/INF_file_format) — the `.inf`
  sidecar metadata format.

## License

MIT — see [LICENSE](LICENSE).

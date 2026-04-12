# oaknut

Python tools for Acorn computer filesystems, files, and formats — the BBC Micro, Electron, Archimedes, and their descendants.

This repository is a [`uv`](https://github.com/astral-sh/uv) workspace monorepo containing the `oaknut-*` family of packages. Each package is independently published to PyPI, but they all contribute to a shared `oaknut.` Python namespace so that imports read naturally:

```python
from oaknut.file import AcornMeta, MetaFormat
from oaknut.dfs import DFS
from oaknut.adfs import ADFS
from oaknut.afs import AFS
from oaknut.basic import tokenise
from oaknut.zip import extract_archive
```

## Packages

| PyPI distribution | Import path | Scope |
|---|---|---|
| [`oaknut-file`](packages/oaknut-file/) | `oaknut.file` | Acorn file metadata handling: INF sidecars, filename encoding, xattrs, and access flags |
| [`oaknut-discimage`](packages/oaknut-discimage/) | `oaknut.discimage` | Disc image sector abstractions shared by Acorn filesystem packages |
| [`oaknut-basic`](packages/oaknut-basic/) | `oaknut.basic` | BBC BASIC tokeniser and detokeniser for Acorn 8-bit and 32-bit BASIC source files |
| [`oaknut-dfs`](packages/oaknut-dfs/) | `oaknut.dfs` | Python library for handling Acorn DFS disc images (SSD/DSD format) |
| [`oaknut-adfs`](packages/oaknut-adfs/) | `oaknut.adfs` | Acorn ADFS disc image support for Archimedes, RISC OS, and BBC Master |
| [`oaknut-zip`](packages/oaknut-zip/) | `oaknut.zip` | Work with ZIP files containing Acorn computer metadata |
| [`oaknut-afs`](packages/oaknut-afs/) | `oaknut.afs` | Acorn Level 3 File Server (AFS) filesystem support — the private on-disc format WFSINIT prepares in the tail of an old-map ADFS disc |
| [`oaknut-disc`](packages/oaknut-disc/) | `oaknut.disc` | CLI for working with Acorn DFS, ADFS, and AFS disc images |

The dependency arrows run strictly bottom-up: `file → discimage → {dfs, adfs} → afs`, with `basic` feeding into `dfs` and `adfs`, and `zip` depending only on `file`. The `disc` CLI package depends on all library packages.

## Quickstart: opening a disc

```python
from oaknut.dfs import DFS
from oaknut.dfs.formats import ACORN_DFS_40T_SINGLE_SIDED

# Create a blank 40-track single-sided DFS image in memory. The
# catalogue is initialised empty with the supplied title.
dfs = DFS.create(ACORN_DFS_40T_SINGLE_SIDED, title="WELCOME")

# Files live under the catalogue root. The "$" directory is the
# default if you write a bare filename.
(dfs.root / "HELLO").write_bytes(b'PRINT "Hello, World!"')

print(f"title:        {dfs.title!r}")
print(f"files:        {[str(f.path) for f in dfs.files]}")
print(f"free_sectors: {dfs.free_sectors}")
```

Output:

```text
title:        'WELCOME'
files:        ['$.HELLO']
free_sectors: 397
```

## Quickstart: Acorn file metadata

```python
from oaknut.file import AcornMeta

# A RISC OS file with the ArtWorks filetype (0xD94) stamped into its
# load address. The bottom byte is the low half of the date word.
meta = AcornMeta(load_addr=0xFFFD9400, exec_addr=0xFFF12345)

print(f"load_addr:         0x{meta.load_addr:08X}")
print(f"filetype-stamped:  {meta.is_filetype_stamped}")
print(f"inferred filetype: 0x{meta.infer_filetype():03X}")
```

Output:

```text
load_addr:         0xFFFD9400
filetype-stamped:  True
inferred filetype: 0xD94
```

## The `disc` CLI

The `oaknut-disc` package provides a unified command-line tool for working with Acorn disc images:

```sh
# List contents of a DFS floppy
disc ls games.ssd '$'

# Copy a file between a DFS floppy and an ADFS hard disc
disc cp games.ssd:'$.ELITE' scsi0.dat:'$.Elite'

# Create and initialise a Level 3 File Server disc
disc create scsi0.dat --format adfs-hard --capacity 10MiB --title Server
disc afs-init scsi0.dat --disc-name Server --cylinders 309 \
  --user Syst:S --user RJS:2MiB \
  --emplace Library --emplace Library1

# View both ADFS and AFS partitions
disc tree scsi0.dat
```

The tool supports DFS, ADFS, and AFS transparently, with filing-system prefix dispatch (`afs:$`, `adfs:$`, `dfs:$`) for dual-partition images. Acorn star-aliases (`*CAT`, `*DELETE`, `*RENAME`, etc.) are accepted alongside their Unix equivalents.

## Development

```sh
git clone https://github.com/rob-smallshire/oaknut.git
cd oaknut
uv sync
uv run pytest
```

The workspace uses `[tool.uv.sources]` in the root `pyproject.toml` to wire sibling packages as local path dependencies during development, so any change in one package is immediately visible to the others without a publish round-trip. End users installing from PyPI get the published versions resolved normally.

Guidance for working on the codebase lives in [`CLAUDE.md`](CLAUDE.md) at the workspace root, with package-specific addenda in `packages/<name>/CLAUDE.md`.

## Installing from PyPI

Install the whole family with [`uv`](https://github.com/astral-sh/uv):

```sh
uv add oaknut
```

Or install individual packages as needed:

```sh
uv add oaknut-dfs        # DFS floppy images only
uv add oaknut-adfs       # ADFS floppy and hard disc images
uv add oaknut-disc       # the disc CLI tool
```

With pip:

```sh
pip install oaknut        # everything
pip install oaknut-disc   # just the CLI
```

## Documentation

- [**Online docs**](https://rob-smallshire.github.io/oaknut/) — CLI guide, cookbook, and API reference
- [`docs/cli-design.md`](docs/cli-design.md) — CLI design rationale
- [`docs/monorepo.md`](docs/monorepo.md) — monorepo architecture

## Licence

MIT. See each package's `LICENSE` file.

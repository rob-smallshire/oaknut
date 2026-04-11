# oaknut

Python tools for Acorn computer filesystems, files, and formats — the BBC Micro, Electron, Archimedes, and their descendants.

This repository is a [`uv`](https://github.com/astral-sh/uv) workspace monorepo containing the `oaknut-*` family of packages. Each package is independently published to PyPI, but they all contribute to a shared `oaknut.` Python namespace so that imports read naturally:

```python
from oaknut.file import AcornMeta, MetaFormat
from oaknut.dfs import DFS
from oaknut.adfs import ADFS
from oaknut.basic import tokenise
from oaknut.zip import extract_archive
```

## Packages

| PyPI distribution | Import path | Scope |
|---|---|---|
| [`oaknut-file`](packages/oaknut-file/) | `oaknut.file` | Acorn file metadata handling: INF sidecars, filename encoding, xattrs, and access flags |
| [`oaknut-discimage`](packages/oaknut-discimage/) | `oaknut.discimage` | Disc image sector abstractions shared by Acorn filesystem packages |
| [`oaknut-basic`](packages/oaknut-basic/) | `oaknut.basic` | BBC BASIC tokeniser and detokeniser for Acorn 8-bit and 32-bit BASIC source files |
| [`oaknut-dfs`](packages/oaknut-dfs/) | `oaknut.dfs` | Python library for handling Acorn DFS disc images (SSD/DSD format) and ADFS disc images |
| [`oaknut-adfs`](packages/oaknut-adfs/) | `oaknut.adfs` | Acorn ADFS disc image support for Archimedes, RISC OS, and BBC Master |
| [`oaknut-zip`](packages/oaknut-zip/) | `oaknut.zip` | Work with ZIP files containing Acorn computer metadata |

The dependency arrows run strictly bottom-up: `file → {discimage, basic} → {dfs, adfs, zip}`. `oaknut-dfs` and `oaknut-adfs` are independent siblings — neither depends on the other.

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

Each library package is independently installable:

```sh
pip install oaknut-file
pip install oaknut-basic
pip install oaknut-dfs
pip install oaknut-adfs
pip install oaknut-zip
```

Or install the whole family via the meta-distribution:

```sh
pip install oaknut
```

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — workspace conventions, development commands, test infrastructure
- [`docs/monorepo.md`](docs/monorepo.md) — monorepo design and architectural target
- [`docs/cli-design.md`](docs/cli-design.md) — design of the forthcoming `disc` CLI

## Licence

MIT. See each package's `LICENSE` file.

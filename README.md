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
| [`oaknut-cli`](packages/oaknut-cli/) | `oaknut.cli` | Shared CLI toolkit for the oaknut family: the contributed-command axis and report-rendering helpers a disc command needs, below the filesystem packages |
| [`oaknut-disc`](packages/oaknut-disc/) | `oaknut.disc` | CLI for working with Acorn DFS, ADFS, and AFS disc images |
| [`oaknut-exception`](packages/oaknut-exception/) | `oaknut.exception` | Categorised exceptions and CLI error-reporting boundary for the oaknut package family |
| [`oaknut-extension`](packages/oaknut-extension/) | `oaknut.extension` | Entry-point plug-in framework shared by every extensible axis of the oaknut package family |
| [`oaknut-filesystem`](packages/oaknut-filesystem/) | `oaknut.filesystem` | The pluggable filesystem contract for the oaknut family: detection, capabilities, geometry, partitions, and the identification coordinator |
| [`oaknut-romfs`](packages/oaknut-romfs/) | `oaknut.romfs` | Python library for Acorn ROM Filing System (ROMFS) paged-ROM images |

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
meta = AcornMeta(load_address=0xFFFD9400, exec_address=0xFFF12345)

print(f"load_address:      0x{meta.load_address:08X}")
print(f"filetype-stamped:  {meta.is_filetype_stamped}")
print(f"inferred filetype: 0x{meta.infer_filetype():03X}")
```

Output:

```text
load_address:      0xFFFD9400
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

Pick the `oaknut-*` packages you actually need. With [`uv`](https://github.com/astral-sh/uv):

```sh
uv add oaknut-disc       # the disc CLI tool (most users want this)
uv add oaknut-dfs        # DFS floppy images
uv add oaknut-adfs       # ADFS floppy and hard disc images
uv add oaknut-afs        # Level 3 File Server discs
uv add oaknut-zip        # ZIP archives carrying Acorn metadata
uv add oaknut-basic      # BBC BASIC tokeniser / detokeniser
```

Or with pip:

```sh
pip install oaknut-disc
```

The bare `oaknut` distribution on PyPI is a **namespace placeholder** — it
ships no code and has no dependencies. It exists only to own the `oaknut`
name on PyPI alongside the family. `pip install oaknut` will succeed and
install nothing useful; install the specific `oaknut-*` package you want
instead.

## Documentation

- [**Online docs**](https://rob-smallshire.github.io/oaknut/) — CLI guide, cookbook, and API reference
- [`docs/dev/cli-design.md`](docs/dev/cli-design.md) — CLI design rationale
- [`docs/dev/monorepo.md`](docs/dev/monorepo.md) — monorepo architecture
- [`docs/dev/basic-tokeniser.md`](docs/dev/basic-tokeniser.md) — BBC BASIC tokeniser/de-tokeniser internals

## Credits and thanks

oaknut stands on decades of Acorn documentation and preservation work. In particular:

- The **New Advanced User Guide** (Acorn Computers) — the primary published reference for the ROM Filing System's on-ROM format and its `&0D`/`&0E` service handler. Note that the service-handler example it prints loops `*CAT` indefinitely when the ROM is fitted in sideways socket 0; oaknut's generated handler corrects this with the `CMP #&10` guard that the genuine Acornsoft ROMs carry (see [`packages/oaknut-romfs/docs/romfs-format-spec.md`](packages/oaknut-romfs/docs/romfs-format-spec.md)).
- **Dominic Beesley** — for the friendly cross-project collaboration on the ROM filing system, including confirming and fixing the socket-0 `*CAT` defect.
- **J.G. Harston**'s [MakeRFS and the mdfs.net documentation](https://mdfs.net/) — a second ROMFS writer and an extensive, careful reference for Acorn filing-system internals.
- **tobylobster**'s [annotated disassembly of Acorn MOS 1.20](https://tobylobster.github.io/mos/) — the authoritative reader-side reference for the ROM filing system's service-call behaviour.
- **`dasmos`** — the tracing disassembler used to compare service handlers byte for byte.

## Licence

MIT. See each package's `LICENSE` file.

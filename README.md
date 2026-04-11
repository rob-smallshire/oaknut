# oaknut

Python tools for Acorn computer filesystems, files, and formats — the BBC Micro, Electron, Archimedes, and their descendants.

This repository is a `uv` workspace monorepo containing the `oaknut-*` family of packages. Each package is independently published to PyPI, but they all contribute to a shared `oaknut.` Python namespace so that imports read naturally:

```python
from oaknut.file import AcornMeta, MetaFormat
from oaknut.dfs import DFS, DFSPath
from oaknut.zip import extract_archive
```

## Packages

| PyPI distribution | Import path | Scope |
|---|---|---|
| [`oaknut-file`](packages/oaknut-file/) | `oaknut.file` | Acorn file metadata — INF sidecars (traditional + PiEconetBridge), filename encoding, xattr namespaces, access flags, host bridge |
| [`oaknut-dfs`](packages/oaknut-dfs/) | `oaknut.dfs` | Acorn DFS / Watford DDFS disc images (SSD, DSD), and ADFS disc images (pending extraction into a dedicated `oaknut-adfs` package) |
| [`oaknut-zip`](packages/oaknut-zip/) | `oaknut.zip` | ZIP archives containing Acorn files — SparkFS extras, INF resolution, RISC OS filetype decoding |

Planned additional packages (see `docs/monorepo.md`):

- `oaknut-fs` — universal filesystem abstractions (catalogue ABC, Acorn codec, boot options)
- `oaknut-image` — disc-image abstractions (sector access, geometry, free-space maps)
- `oaknut-adfs` — ADFS (extracted from the current `oaknut-dfs`)
- `oaknut-basic` — BBC BASIC tokeniser / detokeniser
- `oaknut-disc` — the `disc` CLI binary

## Quick start

```sh
git clone https://github.com/rob-smallshire/oaknut.git
cd oaknut
uv sync
uv run pytest
```

The workspace uses [uv](https://github.com/astral-sh/uv) for dependency management. Sibling packages are wired together as path dependencies during development via `[tool.uv.sources]` in the workspace-root `pyproject.toml`, so any change in one package is immediately visible to the others without a publish round-trip.

## Installing from PyPI

Each library package is independently installable:

```sh
pip install oaknut-file
pip install oaknut-dfs
pip install oaknut-zip
```

Or install the whole family via the meta-distribution:

```sh
pip install oaknut
```

## Documentation

- [`docs/monorepo.md`](docs/monorepo.md) — monorepo design, architectural target, package layering
- [`docs/cli-design.md`](docs/cli-design.md) — design of the forthcoming `disc` CLI

## Licence

MIT. See each package's `LICENSE` file.

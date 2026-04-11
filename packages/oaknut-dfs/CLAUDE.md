# CLAUDE.md — oaknut-dfs

This file provides guidance to Claude Code when working specifically
in `packages/oaknut-dfs/`. The top-level `CLAUDE.md` at the workspace
root has the cross-cutting rules (PEP 420 namespace guard, commit
style, variable naming suffixes, British "disc" spelling, etc.) —
read that first; this file only adds what is specific to the DFS
package.

## Scope after the shared-layer refactor

`oaknut-dfs` hosts Acorn DFS, Watford DDFS, and Opus DDOS support —
the flat-catalogue filesystems used on BBC Micro and Acorn Electron
floppies (.ssd / .dsd). It depends on:

- `oaknut-file` — for `AcornMeta`, `MetaFormat`, `Access`, `FSError`,
  `BootOption`, the `'acorn'` text codec, and the `host_bridge`
  import/export cascade.
- `oaknut-discimage` — for `Surface`, `SectorsView`, `UnifiedDisc`, the
  generic `DiskFormat` dataclass, and `SurfaceSpec` helpers.
- `oaknut-basic` — for BBC BASIC tokenisation used by
  `DFSPath.read_basic` / `write_basic`.

The ADFS filesystem and its directory/free-space-map code live in
the sibling `oaknut-adfs` package. `from oaknut.dfs import ADFS` no
longer works — import ADFS from `oaknut.adfs` instead.

## Architecture (DFS-specific modules)

Every module below lives under `src/oaknut/dfs/`:

- `dfs.py` — user-facing `DFS` class + `DFSPath` + `DFSStat`.
  Methods mirror DFS star commands (`load`, `save`, `delete`,
  `rename`, `lock`, `unlock`, etc.). Format detection from file
  size and extension lives here.
- `catalogue.py` — the DFS catalogue ABC: `Catalogue`, `FileEntry`,
  `DiskInfo`, `ParsedFilename`. DFS-specific shape (31-file cap,
  single-char directories, 7-char filenames, cycle_number) — not
  shared with ADFS, which has its own directory hierarchy in
  `oaknut.adfs`.
- `acorn_dfs_catalogue.py` — concrete `Catalogue` subclass for the
  standard Acorn DFS catalogue layout (sectors 0-1, 31 files).
- `watford_dfs_catalogue.py` — concrete subclass for Watford DDFS
  (62 files, extended catalogue in sectors 2-3).
- `catalogued_surface.py` — wraps a `Surface` with a `Catalogue`,
  giving the mid-level API that `dfs.py` builds on.
- `formats.py` — DFS and Watford format constants. Imports the
  generic `DiskFormat` + surface-spec helpers from
  `oaknut.discimage.formats`.
- `exceptions.py` — `DFSError` base + DFS-specific subclasses
  (`CatalogError`, `DiskFullError`, `FileLocked`,
  `InvalidFormatError`, `FileExistsError`, `CatalogFullError`,
  `CatalogReadError`). All derive from the shared `FSError` base in
  `oaknut.file.exceptions`.

## Layer flow

```
DFS (dfs.py)
  ↓
CataloguedSurface (catalogued_surface.py)
  ↓
Catalogue ABC (catalogue.py)  ←  AcornDFSCatalogue / WatfordDFSCatalogue
  ↓                                         ↓
Surface (oaknut.discimage.surface)    ←  (reads catalogue sectors)
  ↓
SectorsView (oaknut.discimage.sectors_view)
  ↓
raw bytes / mmap
```

Dependencies flow strictly downward. Every module only imports from
the layer directly below it.

## Testing

DFS tests live under `tests/` and import shared workspace fixtures
from the `tests.fixtures` module at the workspace root (reference
images, BeebEm images). Each test file's `conftest.py` injects both
the package's own tests dir and the workspace root into `sys.path`
because pytest's `importlib` mode does not auto-inject them.

```sh
uv run pytest packages/oaknut-dfs/tests -q
```

Cross-cutting integration suites like `test_beebem_images.py` that
exercise both DFS and ADFS reading paths stay here, since they lean
more heavily on DFS.

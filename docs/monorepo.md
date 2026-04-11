# oaknut-* monorepo — Design Document

**Status:** draft for iteration. Nothing here is decided — flag anything you want to change. Amend this file in place; commit history is the discussion log.

## Context

The `oaknut-*` family already spans three published packages — `oaknut-file`, `oaknut-dfs`, `oaknut-zip` — and is on track to grow to six or more once `oaknut-adfs` is split out from `oaknut-dfs`, `oaknut-basic` is extracted from `oaknut_dfs.basic`, and `oaknut-disc` is created as the dedicated home for the CLI (see `cli-design.md`).

Today each package lives in its own git repository. With three packages this is manageable; with six, the per-repo coordination tax starts to hurt:

- Cross-package refactors (e.g. add a new `MetaFormat` to `oaknut-file` and update `oaknut-dfs`, `oaknut-zip`, and `oaknut-disc` to consume it) require manual sequencing of multiple PRs across multiple repos, with no atomic commit binding them.
- CI runs in isolation per repo; integration testing across the family means publishing dev builds to TestPyPI or wiring up cross-repo CI triggers, both of which are friction.
- A newcomer who wants to understand "the oaknut project" has to clone three to six repos and infer how they fit together.
- Shared tooling (ruff config, pre-commit hooks, release scripts, CLAUDE.md guidance) drifts out of sync across repos.
- Documentation that spans the family (architecture overviews, format specs, CLI design) has no natural home.

A monorepo collapses the coordination tax by putting every package under one git history with one CI pipeline, while keeping each package independently publishable to PyPI. This document proposes the layout, migration approach, tooling, and release flow.

The repo is named **`oaknut`** (the bare name is available on PyPI as well, leaving the door open if we ever want a meta-distribution that pulls in the family). Inside the repo each package lives under `packages/oaknut-<name>/` and contributes to a shared **PEP 420 implicit namespace package** so that every library imports under a single `oaknut.` root.

---

## Import paths: PEP 420 namespace packages

PyPI distribution names and Python import paths are decoupled. A user runs `pip install oaknut-dfs` (PyPI distribution) and the code says `from oaknut.dfs import DFS` (import path). This mirrors the convention used by `azure-storage-blob` → `azure.storage.blob`, `google-cloud-storage` → `google.cloud.storage`, and the historical `zope.*` family.

Mechanically, every package's source tree is laid out as:

```
packages/oaknut-dfs/
├── pyproject.toml                     # name = "oaknut-dfs"
└── src/
    └── oaknut/                        # NAMESPACE — must NOT contain __init__.py
        └── dfs/                       # regular package
            ├── __init__.py
            ├── catalogue.py
            ├── ...
```

The `src/oaknut/` directory is the namespace root and **must never contain an `__init__.py` in any package**. PEP 420 merges all the `src/oaknut/` contributions across installed distributions into a single virtual `oaknut` package at import time. The instant any package ships `oaknut/__init__.py`, the namespace collapses and the other packages' subpackages stop being importable. This is the single biggest footgun of namespace packaging and it's worth a CLAUDE.md guard rule plus a CI check that fails the build if any `src/oaknut/__init__.py` ever appears in a commit.

The mapping from PyPI distribution to import path is one-to-one and predictable:

| PyPI distribution | Import path |
|---|---|
| `oaknut-file`  | `oaknut.file` |
| `oaknut-fs`    | `oaknut.fs` |
| `oaknut-image` | `oaknut.image` |
| `oaknut-dfs`   | `oaknut.dfs` |
| `oaknut-adfs`  | `oaknut.adfs` |
| `oaknut-basic` | `oaknut.basic` |
| `oaknut-zip`   | `oaknut.zip` |
| `oaknut-disc`  | `oaknut.disc` |

Each package's `pyproject.toml` discovers its sub-package via setuptools' namespace-aware finder:

```toml
[tool.setuptools.packages.find]
where = ["src"]
include = ["oaknut.*"]
namespaces = true
```

(Modern setuptools defaults are namespace-aware, so this is largely belt-and-braces, but being explicit prevents accidents.)

**Breaking change for existing packages.** This is a hard import-path migration: today's `from oaknut_file import AcornMeta` becomes `from oaknut.file import AcornMeta`. We do not offer a transitional `oaknut_file` shim — every consumer updates in one go. This warrants a coordinated major-version bump across the family at the first release from the monorepo (e.g. `oaknut-file` 0.1 → 1.0, `oaknut-dfs` 3.x → 4.0, `oaknut-zip` → 1.0). The current 3.0 alpha state of `oaknut-dfs` makes the timing right; later is harder.

The CLI script entry points (`disc`, `oaknut-disc`) are unaffected by the import-path change — they're PyPI script names, not import paths. Their target callable is updated from a hypothetical `oaknut_disc.cli:cli` to `oaknut.disc.cli:cli`.

---

## Architectural target: shared layers for filesystem packages

The end-state package set is layered, not flat. Beyond the packages that already exist or are explicitly planned (`oaknut-file`, `oaknut-dfs`, `oaknut-zip`, `oaknut-disc`, `oaknut-basic`, `oaknut-adfs`), there are **two new shared lower-layer packages** that hold the abstractions today's `oaknut-dfs` exposes for both DFS and ADFS:

| Package | Scope | Used by |
|---|---|---|
| `oaknut-file` | Acorn file metadata sidecar formats: INF (trad + PiEconetBridge), `user.acorn.*` / `user.econet_*` xattrs, RISC OS / MOS filename encoding, `Access` flags, `AcornMeta`, `MetaFormat`, **and the host bridge** (the `host_bridge.py` module currently inside `oaknut-dfs` moves here, since it's a natural extension of oaknut-file's I/O surface) | `oaknut-dfs`, `oaknut-adfs`, `oaknut-zip`, anything that touches host metadata |
| `oaknut-fs` *(new)* | **Universal filesystem abstractions** — anything an Acorn filesystem needs that isn't filesystem-specific: the abstract `Catalogue` ABC, `FileEntry`, `DiskInfo`, `ParsedFilename`, the `acorn` text codec, `BootOption`, `FSError` base | `oaknut-dfs`, `oaknut-adfs`, future `oaknut-nfs`, future `oaknut-afs` |
| `oaknut-image` *(new)* | **Disc-image abstractions** for filesystems backed by sectors on a disc image: `Surface`, `SectorImage`, `SectorsView`, `DiskFormat`, geometry helpers, `UnifiedDisc`, `CataloguedSurface` | `oaknut-dfs`, `oaknut-adfs` only — *not* `oaknut-nfs`/`oaknut-afs`, neither of which is disc-based |
| `oaknut-dfs` | DFS / Watford DDFS / Opus DDOS only — the catalogue implementations and `DFSPath` / `DFS` types | downstream consumers |
| `oaknut-adfs` | ADFS only — directory format, free space map, `ADFSPath` / `ADFS` types | downstream consumers |
| `oaknut-basic` | BBC BASIC tokeniser/detokeniser, language constants. Self-contained, no internal deps | downstream consumers |
| `oaknut-zip` | Acorn-aware ZIP archive support (SparkFS extras, INF resolution) | CLI |
| `oaknut-disc` | The CLI binary (`disc` / `oaknut-disc`) — depends on whichever filesystem packages it wants to support | end users |

**Why two shared lower layers (`oaknut-fs` and `oaknut-image`) rather than one?** The clean property of the split is that **`oaknut-nfs` and `oaknut-afs` could be implemented later without ever depending on `oaknut-image`**. Acorn NFS (Econet network filing) and AFS (file server) have no disc image — they have a network protocol or a server-side store. Lumping the disc abstractions into a single shared `oaknut-fs` package would force NFS/AFS to pull in code they fundamentally don't use, and would muddy the answer to "what does NFS need from us?". Two packages document the boundary between "any Acorn filesystem" and "specifically a disc-based one" at the package level rather than in prose comments.

**Where today's code goes.** Mapping the current `src/oaknut_dfs/` modules onto the target layout, with the new namespace-package import path each one ends up at:

| Current module | Target distribution | Target import path |
|---|---|---|
| `acorn_encoding.py` | `oaknut-fs` | `oaknut.fs.encoding` |
| `boot_option.py` | `oaknut-fs` | `oaknut.fs.boot_option` |
| `catalogue.py` (`Catalogue` ABC, `FileEntry`, `DiskInfo`, `ParsedFilename`) | `oaknut-fs` | `oaknut.fs.catalogue` |
| `exceptions.py` (`FSError` base; format-specific subclasses follow their format) | `oaknut-fs` (base) + `oaknut-dfs`/`oaknut-adfs` (subclasses) | `oaknut.fs.exceptions` + `oaknut.dfs.exceptions` etc. |
| `host_bridge.py` | `oaknut-file` | `oaknut.file.host_bridge` |
| `sectors_view.py`, `surface.py`, `catalogued_surface.py` | `oaknut-image` | `oaknut.image.{sectors_view,surface,catalogued_surface}` |
| `formats.py` (`DiskFormat` and the `ACORN_DFS_*` constants) | `oaknut-image` (base) + `oaknut-dfs` (DFS-specific constants) | `oaknut.image.formats` + `oaknut.dfs.formats` |
| `unified_disc.py` | `oaknut-image` | `oaknut.image.unified_disc` |
| `acorn_dfs_catalogue.py`, `watford_dfs_catalogue.py`, `dfs.py` | `oaknut-dfs` | `oaknut.dfs.*` |
| `adfs.py`, `adfs_directory.py`, `adfs_free_space_map.py` | `oaknut-adfs` | `oaknut.adfs.*` |
| `basic.py` | `oaknut-basic` | `oaknut.basic` |

This layering is the **architectural target**, not day-one work. The monorepo migration itself only needs to import the existing repos as they stand. The shared-layer extractions (`oaknut-fs`, `oaknut-image`, the move of `host_bridge` into `oaknut-file`) happen as a follow-up once the monorepo is in place — they're one of the things the monorepo makes much easier, because they're cross-package refactors that can land in single atomic commits.

---

## Goals

1. **One repo, one history, one CI.** Cross-package changes land in single commits/PRs.
2. **Independent PyPI releases per package.** Versioning is per-package; tags are namespaced.
3. **Preserve existing per-file git history** during the migration so `git blame` and `git log` continue to work for code that pre-existed in the standalone repos.
4. **Editable path-dep development loop** — sibling packages reference each other as path deps during development, matching the existing "use local path deps during dev, publish to PyPI only when everything works" preference.
5. **Single shared tooling configuration** (`ruff`, `pytest`, pre-commit, release scripts) at the workspace root, with per-package overrides where genuinely needed.
6. **No regression for existing PyPI users.** The published packages keep their names, their import paths, their release cadence, and their changelogs.

## Non-goals

- A unified version number across packages (each package versions independently — `oaknut-file` at 0.1.4 doesn't need to bump just because `oaknut-dfs` released).
- Merging the packages themselves into one mega-package. The point of the split is *more* small focused packages, not fewer.
- Vendoring third-party dependencies.
- A custom build system. Stay on `uv` + `setuptools` (or `hatchling`, if we want to switch — orthogonal decision).

---

## Proposed layout

```
oaknut/                                  # monorepo root
├── README.md                            # family overview, links to each package
├── pyproject.toml                       # workspace root (uv workspace declaration)
├── CLAUDE.md                            # shared guidance for Claude Code
├── .pre-commit-config.yaml              # shared hooks (incl. namespace guard)
├── ruff.toml                            # shared lint config
├── docs/
│   ├── cli-design.md                    # cross-cutting docs live here
│   ├── monorepo.md                      # this file
│   └── architecture/                    # whole-family architecture notes
├── packages/
│   ├── oaknut-file/                     # metadata sidecars + host bridge
│   │   ├── pyproject.toml               # name = "oaknut-file"
│   │   ├── README.md
│   │   ├── src/oaknut/file/             # NOTE: NO src/oaknut/__init__.py
│   │   │   ├── __init__.py
│   │   │   └── ...
│   │   ├── tests/
│   │   └── docs/                        # package-specific docs only
│   ├── oaknut-fs/                       # universal filesystem ABCs (NEW)
│   │   ├── pyproject.toml               # name = "oaknut-fs"
│   │   ├── src/oaknut/fs/
│   │   │   ├── __init__.py
│   │   │   └── ...
│   │   └── tests/
│   ├── oaknut-image/                    # disc-image abstractions (NEW)
│   │   ├── pyproject.toml               # name = "oaknut-image"
│   │   ├── src/oaknut/image/
│   │   │   ├── __init__.py
│   │   │   └── ...
│   │   └── tests/
│   ├── oaknut-dfs/                      # DFS / Watford DDFS / Opus DDOS only
│   │   ├── pyproject.toml               # name = "oaknut-dfs"
│   │   ├── src/oaknut/dfs/
│   │   │   ├── __init__.py
│   │   │   └── ...
│   │   └── tests/
│   ├── oaknut-adfs/                     # extracted from today's oaknut-dfs
│   │   ├── pyproject.toml               # name = "oaknut-adfs"
│   │   ├── src/oaknut/adfs/
│   │   └── tests/
│   ├── oaknut-basic/                    # BBC BASIC tokeniser
│   │   ├── pyproject.toml               # name = "oaknut-basic"
│   │   ├── src/oaknut/basic/
│   │   └── tests/
│   ├── oaknut-zip/                      # name = "oaknut-zip"
│   │   ├── pyproject.toml
│   │   ├── src/oaknut/zip/
│   │   └── tests/
│   └── oaknut-disc/                     # CLI
│       ├── pyproject.toml               # name = "oaknut-disc"
│       ├── src/oaknut/disc/
│       │   ├── __init__.py
│       │   └── cli.py
│       └── tests/
└── scripts/
    ├── release.sh                       # per-package release helper
    ├── check_no_namespace_init.sh       # CI guard: no oaknut/__init__.py allowed
    └── ...
```

The repeated **"NOTE: NO `src/oaknut/__init__.py`"** is the most important convention in the layout. Each package contributes a regular sub-package (`src/oaknut/<name>/__init__.py` is fine and expected) but the namespace root above it stays empty. A pre-commit hook and a CI step both run `scripts/check_no_namespace_init.sh`, which fails if `find packages/*/src/oaknut -maxdepth 1 -name __init__.py` returns any results.

The dependency arrows are layered cleanly:

```
                  ┌──────────────┐
                  │ oaknut-disc  │  (CLI)
                  └──────┬───────┘
                         │
       ┌─────────────────┼──────────────────┬──────────────┐
       │                 │                  │              │
       ▼                 ▼                  ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  oaknut-dfs  │  │  oaknut-adfs │  │  oaknut-zip  │  │ oaknut-basic │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────────────┘
       │                 │                  │
       ├─────────────────┤                  │
       ▼                 ▼                  │
┌──────────────┐  ┌──────────────┐          │
│ oaknut-image │  │  oaknut-fs   │          │
└──────────────┘  └──────────────┘          │
       │                 │                  │
       └────────┬────────┴──────────────────┘
                ▼
        ┌──────────────┐
        │ oaknut-file  │
        └──────────────┘
```

Future `oaknut-nfs` and `oaknut-afs` would slot in alongside `oaknut-dfs`/`oaknut-adfs` but depend only on `oaknut-fs` (and `oaknut-file`), bypassing `oaknut-image` entirely.

The workspace root `pyproject.toml` declares `[tool.uv.workspace]` listing the member packages, plus the shared dev/test dependency groups. Each package's own `pyproject.toml` keeps its real metadata, classifiers, and runtime dependencies — the workspace root only orchestrates.

---

## Tooling: `uv` workspaces

`uv` natively supports the workspace pattern we want, and the layout below is validated against an in-house reference monorepo (`~/Code/sixty-north/tubetrain`) that has been running uv workspaces with PEP 420 namespace packages in production. Most of the configuration choices are copied from there.

### Workspace root `pyproject.toml`

```toml
# /pyproject.toml
[project]
name = "oaknut"
version = "0.0.1"
requires-python = ">= 3.11"
# Optional meta-distribution: pip install oaknut → install everything.
dependencies = [
    "oaknut-file",
    "oaknut-fs",
    "oaknut-image",
    "oaknut-dfs",
    "oaknut-adfs",
    "oaknut-basic",
    "oaknut-zip",
    "oaknut-disc",
]

[tool.uv.workspace]
members = ["packages/oaknut-*"]

[tool.uv.sources]
oaknut-file  = { workspace = true }
oaknut-fs    = { workspace = true }
oaknut-image = { workspace = true }
oaknut-dfs   = { workspace = true }
oaknut-adfs  = { workspace = true }
oaknut-basic = { workspace = true }
oaknut-zip   = { workspace = true }
oaknut-disc  = { workspace = true }

[tool.uv]
default-groups = ["test", "lint", "dev"]

[dependency-groups]
test = [
    "pytest>=8.3",
    "pytest-cov>=5",
]
lint = [
    "ruff>=0.9",
]
dev = [
    "pre-commit>=3",
    "bump-my-version>=0.28",
]

[tool.pytest.ini_options]
# importlib mode is required for namespace packages — the legacy
# prepend/append modes don't reliably handle PEP 420 namespaces.
addopts = ["--import-mode=importlib"]
testpaths = [
    "packages/oaknut-file/tests",
    "packages/oaknut-fs/tests",
    "packages/oaknut-image/tests",
    "packages/oaknut-dfs/tests",
    "packages/oaknut-adfs/tests",
    "packages/oaknut-basic/tests",
    "packages/oaknut-zip/tests",
    "packages/oaknut-disc/tests",
]

[tool.ruff]
line-length = 100
```

Three points worth highlighting:

1. **`--import-mode=importlib` is mandatory**, not optional. Pytest's default `prepend` import mode collides with PEP 420 namespace packages in confusing ways (sibling packages that contribute to the same namespace stop resolving each other). `importlib` mode is what tubetrain uses and what the pytest docs recommend for any project with namespace packages.
2. **`testpaths` are listed explicitly** rather than relying on pytest auto-discovery. This is more reliable in a workspace and matches tubetrain.
3. **The `[project]` block at the workspace root creates an optional `oaknut` meta-distribution.** Its only purpose is `pip install oaknut` as a convenience for users who want the whole family in one command. We can publish it or skip it; tubetrain has one but doesn't publish it. Either way, the meta-distribution is just shorthand — the individual packages remain the canonical units.

### Per-package `pyproject.toml`

Each package's `pyproject.toml` is small and uniform. Setuptools' modern defaults are namespace-aware, so `[tool.setuptools.packages.find] where = ["src"]` is sufficient — no `namespaces = true`, no `include` filter required (confirmed by tubetrain).

```toml
# packages/oaknut-dfs/pyproject.toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "oaknut-dfs"
requires-python = ">= 3.11"
dynamic = ["version"]
description = "Acorn DFS / Watford DDFS / Opus DDOS disc image support."
readme = "README.md"
license = "MIT"
dependencies = [
    "oaknut-file>=1.0",
    "oaknut-fs>=1.0",
    "oaknut-image>=1.0",
]

[tool.setuptools.dynamic]
version = { attr = "oaknut.dfs.__version__" }

[tool.setuptools.packages.find]
where = ["src"]
```

The `version` is sourced via the namespace import path (`oaknut.dfs.__version__`), which matches how each `src/oaknut/<name>/__init__.py` already declares `__version__ = "..."` in tubetrain.

In the workspace, `uv sync` resolves each `oaknut-*` dependency to the local path automatically (via the workspace-root `[tool.uv.sources]`); during a real PyPI install the same dependency string resolves against PyPI. No source-code changes are required to switch between dev and published modes.

### Lockfile policy

Tubetrain commits a top-level `uv.lock` because it's an application-shaped monorepo (web app, CLI, infrastructure). For oaknut, which is **library-shaped end to end**, we follow the existing project rule: **no committed `uv.lock` at any level**. The workspace is a development convenience, not a deployment artefact, and a committed lockfile would over-constrain end-user dependency resolvers when they `pip install oaknut-dfs`. Developers running `uv sync` get a working environment from the deps alone, regenerated on demand.

### `.gitignore` essentials

Two namespace-package-specific entries on top of the usual Python ignores:

```gitignore
# Python bytecode is created at the namespace level too — common gotcha
packages/*/src/oaknut/__pycache__/
packages/*/src/oaknut/*/__pycache__/

# Standard
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
*.egg-info/
```

The first two patterns matter because Python writes `__pycache__` directories at the namespace level alongside the regular sub-packages, and a stray `oaknut/__pycache__/` checked into git looks indistinguishable from a missing-namespace bug at first glance.

---

## Migration: importing existing histories

The three existing repos must be folded into `packages/<name>/` while preserving per-file history. The standard tool is `git filter-repo`.

Per repo, the migration is:

```sh
# In a fresh clone of e.g. oaknut-file
git filter-repo --to-subdirectory-filter packages/oaknut-file
```

This rewrites every commit in that repo so its files appear under `packages/oaknut-file/` instead of at the root. Then in a fresh empty monorepo:

```sh
git remote add oaknut-file ../oaknut-file
git fetch oaknut-file
git merge --allow-unrelated-histories oaknut-file/master
```

Repeat for `oaknut-dfs` and `oaknut-zip`. The result is a single repo with three discrete history lineages converging at the merge commits, and `git log packages/oaknut-file/` shows the original per-file history intact.

`oaknut-adfs`, `oaknut-basic`, and `oaknut-disc` start fresh — they're extracted from today's `oaknut-dfs` source tree as part of the migration commit, after the import. Their history begins at the extraction point, with the pre-extraction history visible by following `git log` back through the `oaknut-dfs` lineage.

---

## Release flow

Each package retains its own version, its own changelog, and its own PyPI release cadence. Tags are namespaced to disambiguate:

```
oaknut-file-v0.1.4
oaknut-dfs-v3.1.0
oaknut-zip-v0.2.0
oaknut-disc-v0.1.0
```

A small `scripts/release.sh <package> <bump>` wrapper invokes `bump-my-version` (already used in `oaknut-dfs`) scoped to that package's `pyproject.toml`, creates the namespaced tag, and runs `uv build` + `uv publish` for that package alone.

CI per-package: a GitHub Actions matrix iterates members, running `uv run --package <name> pytest packages/<name>/tests/` for each. Pull-request CI runs all packages; a release tag (e.g. `oaknut-file-v0.1.4`) gates a publish job that filters to just that package.

---

## Shared tooling

What lives at the workspace root:

- `ruff.toml` — lint rules (per-package overrides via `[tool.ruff]` in the package's own `pyproject.toml` if genuinely needed; default is shared)
- `.pre-commit-config.yaml` — runs ruff, pytest-collect, and any other repo-wide hooks
- `CLAUDE.md` — shared instructions for Claude Code, with package-specific guidance in `packages/<name>/CLAUDE.md` overrides
- `pyproject.toml` — uv workspace declaration and shared dev-dependency group
- `docs/` — cross-cutting documentation (CLI design, format specs, architecture overviews, this monorepo doc)

What stays per-package:

- Real package metadata (name, version, description, classifiers, author, runtime deps)
- Per-package `README.md` (PyPI long-description)
- Per-package `tests/` directory
- Per-package `docs/` for documentation that's truly local to that package's internals (e.g. `oaknut-dfs/docs/dfs-format-spec.md` is only relevant to DFS)

---

## Sequencing

**This migration is a prerequisite for the CLI work** described in `cli-design.md`. The CLI is intended to land in a dedicated `packages/oaknut-disc/` directory inside the monorepo from day one, not first in today's `oaknut-dfs` package and then moved later. Doing it that way avoids a code-relocation step we don't have to take, lets the CLI depend cleanly on whichever library packages it needs (including future `oaknut-adfs`), and means there's never an awkward intermediate state where the CLI lives inside a library package that doesn't quite match its scope.

The migration itself is seven steps:

1. **Stand up the empty monorepo skeleton** at a new path (e.g. `~/Code/oaknut/`), with the workspace root `pyproject.toml`, the namespace-init guard script in `scripts/`, the pre-commit hook, and an empty `packages/` directory.
2. **Import `oaknut-file` first** — it has no internal dependencies and the smallest history. Validate the `git filter-repo` workflow on the smallest target. The import lands the existing `src/oaknut_file/` tree under `packages/oaknut-file/src/oaknut_file/` initially; the namespace-package rename happens in step 5.
3. **Import `oaknut-dfs`** as it stands today (still containing ADFS code). Its dependency on `oaknut-file` switches to the workspace path automatically.
4. **Import `oaknut-zip`**. Same dependency-switching benefit.
5. **Coordinated namespace-package rename.** A single commit per package moves `src/oaknut_file/` → `src/oaknut/file/`, `src/oaknut_dfs/` → `src/oaknut/dfs/`, `src/oaknut_zip/` → `src/oaknut/zip/`, and rewrites every internal `from oaknut_file …`, `from oaknut_dfs …`, `from oaknut_zip …` import to `from oaknut.file …`, `from oaknut.dfs …`, `from oaknut.zip …`. Each `pyproject.toml` gets the namespace-aware `[tool.setuptools.packages.find]` block. The namespace-init guard runs to confirm no `src/oaknut/__init__.py` slipped in. This is the breaking change; everything afterwards uses the new import paths.
6. **Run the full test suite** across all three packages from the monorepo root and confirm parity with the standalone repos (modulo the import-path rewrites).
7. **Tag the cutover.** Publish a coordinated major-version bump (`oaknut-file` → 1.0, `oaknut-dfs` → 4.0, `oaknut-zip` → 1.0) from the monorepo to confirm the per-package release flow works end-to-end. Archive the standalone repos (read-only on GitHub, with a redirect notice in their READMEs pointing at the monorepo and the new `from oaknut.<name>` import idiom).

After step 7 the CLI work from `cli-design.md` can start in `packages/oaknut-disc/` with imports already in their final namespace form (`from oaknut.dfs import DFS`, `from oaknut.file import MetaFormat`, etc.). The shared-layer extractions (`oaknut-fs`, `oaknut-image`) and the package splits (`oaknut-adfs`, `oaknut-basic`) are separate downstream refactors that happen *after* the CLI work without disturbing it — the CLI just keeps depending on `oaknut-dfs` and inherits the new packages transparently as `oaknut-dfs` slims down. Because everything is already namespace-packaged, those downstream extractions are pure intra-namespace `git mv` operations: moving `src/oaknut/dfs/basic.py` from `packages/oaknut-dfs/` to `packages/oaknut-basic/src/oaknut/basic/__init__.py` doesn't change a single import statement at any call site — `from oaknut.basic import tokenise` keeps working unchanged.

That gives us this overall plan:

```
Monorepo migration (this doc)                    <-- prerequisite
        ↓
CLI work in packages/oaknut-disc/                (cli-design.md)
        ↓
Library refactor — architectural target reached:
  • Extract oaknut-fs    (universal filesystem ABCs)
  • Extract oaknut-image (disc-image abstractions)
  • Move host_bridge → oaknut-file
  • Split oaknut-adfs out of oaknut-dfs
  • Split oaknut-basic out of oaknut-dfs
```

The library-refactor steps are easier inside the monorepo than they would be in scattered repos — atomic cross-package refactor commits, one CI run, no inter-repo coordination — which is one of the strongest reasons to do the monorepo migration first.

---

## Open questions

1. **Repo name.** `oaknut`? `oaknut-tools`? `oaknut-mono`? `oaknut-suite`? Plain `oaknut` seems cleanest if the GitHub org/user is available, or it could live as `rob-smallshire/oaknut`.
2. **GitHub org vs personal namespace.** Stay under `rob-smallshire/oaknut`, or set up a `oaknut/` org for the family? Org gives a cleaner long-term home but adds a one-time setup tax and changes issue/PR URLs.
3. **Shared issue tracker vs per-package labels.** A single repo means one issue tracker; consistent labels (`area:dfs`, `area:adfs`, `area:cli`, `area:file`, `area:basic`, `area:zip`) keep filtering possible. Probably the right call.
4. **`uv.lock` policy.** Confirmed: no top-level lockfile, matching the existing per-package rule. But should the *CLI* package (`oaknut-disc`) have one, since CLIs are conceptually closer to applications than libraries? My instinct is still no — `oaknut-disc` is published to PyPI for end users to install, and a committed lockfile would over-constrain their dependency resolver.
5. **`bump-my-version` scope.** Today `oaknut-dfs/pyproject.toml` configures `bump-my-version` to bump `src/oaknut_dfs/__init__.py`. In the monorepo each package keeps its own `[tool.bumpversion]` block scoped to its own files. The `scripts/release.sh` wrapper just runs `cd packages/<name> && bump-my-version bump <part>`.
6. **Pre-existing CLAUDE.md content.** Each package's CLAUDE.md ports over to `packages/<name>/CLAUDE.md`, with the cross-cutting bits (variable naming conventions, commit message rules, project-wide preferences) lifted to the workspace root `CLAUDE.md`.
7. **Memory file path.** Today the project memory lives at `~/.claude/projects/-Users-rjs-Code-oaknut-dfs/memory/`. Once the monorepo path becomes `~/Code/oaknut/`, the memory directory will be different. We should plan a one-time migration of the existing memory entries (the feedback rules in particular) to the new project memory directory rather than losing them.

---

## Out of scope for this migration

- Switching build backend from `setuptools` to `hatchling` or `pdm-backend`. Independent decision.
- Rewriting tests to use shared fixtures across packages. Each package's tests stay in its own `tests/` directory; cross-package integration tests, if needed, get a new top-level `tests/` directory in the workspace root.
- Adopting a unified changelog format. Each package keeps its own changelog.
- Renaming any of the published packages. Names stay as they are on PyPI.
- Auto-generated cross-package API docs. Future work.

---

## Verification (once the migration is agreed)

After step 5 of the sequencing plan above, before any cutover:

1. `uv sync` from the workspace root resolves all sibling deps to local paths and installs each package editable.
2. `uv run pytest` from the workspace root runs every package's tests and they all pass with the same results as the standalone repos.
3. `git log packages/oaknut-file/src/oaknut_file/inf.py` shows the same commit history as `git log src/oaknut_file/inf.py` did in the standalone `oaknut-file` repo.
4. `uv build --package oaknut-file` produces a wheel and sdist identical to what the standalone repo would produce (modulo metadata pointing at the new repo URL).
5. A dry-run release of one package via `scripts/release.sh oaknut-file patch` produces the right tag, the right wheel, and (on `--dry-run`) doesn't actually push to PyPI.
6. From a fresh venv outside the monorepo, `pip install oaknut-dfs==<latest>` from real PyPI continues to work — proving the migration didn't accidentally break the published package.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`oaknut` is a family of Python packages for working with Acorn computer filesystems, files, and formats (BBC Micro, Electron, Archimedes, RISC OS). The repository is a `uv` workspace under `packages/oaknut-*`, each independently publishable to PyPI. All packages contribute to a shared **PEP 420 implicit namespace package** named `oaknut`, so imports read as `from oaknut.dfs import DFS`, `from oaknut.file import AcornMeta`, `from oaknut.adfs import ADFS`, and so on.

See `docs/monorepo.md` for the architectural doc and `docs/cli-design.md` for the forthcoming `disc` CLI design.

## Package layering

Seven packages, layered strictly bottom-up:

| PyPI distribution | Import path | Depends on | Scope |
|---|---|---|---|
| `oaknut-file` | `oaknut.file` | — | INF sidecars, xattr namespaces, filename encoding, `Access`, `AcornMeta`, `MetaFormat`, `BootOption`, `FSError` base, `acorn` text codec, `host_bridge` |
| `oaknut-discimage` | `oaknut.discimage` | `file` | `Surface`, `SectorsView`, `UnifiedDisc`, generic `DiskFormat` + surface-spec helpers |
| `oaknut-basic` | `oaknut.basic` | — | BBC BASIC tokeniser/detokeniser, language constants |
| `oaknut-dfs` | `oaknut.dfs` | `file`, `discimage`, `basic` | Acorn DFS / Watford DDFS / Opus DDOS — flat-catalogue BBC/Electron floppies |
| `oaknut-adfs` | `oaknut.adfs` | `file`, `discimage`, `basic` | ADFS hierarchical directories, free space maps, hard-disc images |
| `oaknut-afs` | `oaknut.afs` | `file`, `discimage`, `adfs` | Acorn Level 3 File Server private on-disc format (`AFS0` magic). Read/write, `wfsinit` partitioning + initialisation, merge, host-tree import, shipped library images, `oaknut-afs-disc` CLI |
| `oaknut-zip` | `oaknut.zip` | `file` | ZIP archives containing Acorn files (SparkFS extras, INF resolution, RISC OS filetypes) |

`oaknut-dfs` and `oaknut-adfs` are independent siblings — `from oaknut.dfs import ADFS` is **intentionally broken**. ADFS lives in `oaknut.adfs`; do not restore the compatibility re-export.

## Critical rule: PEP 420 namespace packages

**No package may ship `src/oaknut/__init__.py`.** Each package's code lives at `src/oaknut/<name>/__init__.py` instead. The `src/oaknut/` directory is the namespace root and must stay empty except for its sub-package directories. If you ever see `packages/<pkg>/src/oaknut/__init__.py`, delete it immediately — it shadows the namespace and breaks every sibling package's imports at install time. The `scripts/check_no_namespace_init.sh` pre-commit hook and CI step guard against this.

## Development

```sh
uv sync                                      # Install all workspace members editable
uv run pytest                                 # Full suite across every package (~1440 tests)
uv run pytest packages/oaknut-dfs/tests       # One package's suite
uv run pytest packages/oaknut-dfs/tests/test_dfs.py::TestDFSFromFile::test_from_file_read_only
                                              # A single test
uv run pytest -k "write_bytes"                # By name substring
uv run ruff check                             # Lint
uv run ruff check --fix                       # Lint + autofix
pre-commit run --all-files                    # Run all hooks (ruff + namespace guard)
```

The workspace uses `[tool.uv.sources]` at the root so sibling deps like `oaknut-file` resolve to local paths during development, and to PyPI for end-user installs — no source changes needed to switch between modes.

## Test infrastructure (non-obvious)

**Pytest runs in `--import-mode=importlib`** (workspace `pyproject.toml`). This is mandatory for PEP 420 namespace packages — the default `prepend` mode collides with sibling packages contributing to the same namespace. Consequence: pytest does not auto-inject test directories into `sys.path`.

Every package's `tests/conftest.py` therefore starts with a `sys.path` injection for **both** the package's own `tests/` directory **and** the workspace root:

```python
_TESTS_DIRPATH = Path(__file__).parent
_WORKSPACE_ROOT = _TESTS_DIRPATH.parent.parent.parent
for _path in (_TESTS_DIRPATH, _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
```

This restores two import patterns:

1. `from helpers.adfs_image import ...` — each package can have its own `tests/helpers/` module (oaknut-adfs does, oaknut-dfs used to).
2. `from tests.fixtures import REFERENCE_IMAGES_DIRPATH, BEEBEM_IMAGES_DIRPATH` — shared test data lives under `tests/` at the workspace root, not inside any one package. The two path constants point at `tests/data/images/` (DFS/ADFS reference images) and `tests/beebem/` (cross-cutting BeebEm corpus). `tests/fixtures.py` only exposes path constants; each package builds its own format-specific loader fixtures on top.

When adding tests that use reference data, import the constant and resolve the filename against it — never hard-code a `Path(__file__).parent / "data" / ...` reference.

## Variable naming conventions

All packages follow these suffix conventions:

- `_filename` — just the name part (e.g. "HELLO")
- `_filepath` — full path to a file (e.g. `Path("/path/to/disc.ssd")`)
- `_dirpath` — a directory path
- `_dirname` — a directory name

Avoid ambiguous `_file` or `_dir` suffixes.

## Prose conventions

Use British "disc" rather than "disk" for Acorn-era subject matter. The project is about physical discs and the filing systems designed for them.

## Commit messages

- Don't mention "Claude", Anthropic, or the underlying model.
- No emojis.
- Focus on the *why* of a change, not the *what*; the diff shows the what.
- Prefer many small, semantically-meaningful commits over one large batch during multi-step refactors.

## Tooling

- Always use `uv` (not `pip` directly, not `poetry`).
- Do **not** commit any `uv.lock` file at any level — these are libraries, not applications, and committed lockfiles over-constrain end-user dependency resolvers.
- Dev dependencies live in `[dependency-groups]` at the workspace root (test, lint, dev). Per-package `pyproject.toml` files declare only their runtime dependencies.
- Each package has its own `[tool.bumpversion]` config scoped to its own `src/oaknut/<name>/__init__.py` and a namespaced tag format (`oaknut-<name>-v{version}`).

## Test-first preference

When implementing a non-trivial change, write a failing test first, then make it pass. This applies equally to bug fixes and new features.

## Git safety

- Never `git push` without being asked. Leave pushes to the user.
- Never skip hooks (`--no-verify`).
- Don't run destructive operations (`git reset --hard`, `git clean -f`, `rm -rf` on version-controlled directories) without being asked.

## Per-package guidance

Package-specific CLAUDE.md files that inherit from this one:

- `packages/oaknut-dfs/CLAUDE.md` — DFS module layout, layer flow, testing entry points.
- `packages/oaknut-zip/CLAUDE.md` — ZIP archive handling specifics.

- `packages/oaknut-afs/CLAUDE.md` — AFS module architecture, primary sources, testing.

The other packages (`oaknut-file`, `oaknut-discimage`, `oaknut-adfs`, `oaknut-basic`) don't currently ship a per-package CLAUDE.md; their scope is described in the layering table above.

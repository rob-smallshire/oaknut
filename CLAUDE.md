# CLAUDE.md — oaknut workspace

This file provides guidance to Claude Code when working in the oaknut monorepo. Per-package guidance lives at `packages/<name>/CLAUDE.md` and inherits from here.

## Project overview

`oaknut` is a family of Python packages for working with Acorn computer filesystems, files, and formats (BBC Micro, Electron, Archimedes, RISC OS). The repository is a `uv` workspace containing members under `packages/oaknut-*`, each independently publishable to PyPI. All packages contribute to a shared **PEP 420 implicit namespace package** named `oaknut`, so imports read as `from oaknut.dfs import DFS`, `from oaknut.file import AcornMeta`, and so on. See `docs/monorepo.md` for the full architectural context.

## Critical rule: PEP 420 namespace packages

**No package may ship `src/oaknut/__init__.py`.** Each package's code lives at `src/oaknut/<name>/__init__.py` instead. The `src/oaknut/` directory is the PEP 420 namespace root and must stay empty except for its sub-package directories.

If you ever see `packages/<pkg>/src/oaknut/__init__.py`, delete it immediately — it shadows the namespace and breaks every sibling package's imports at install time. The `scripts/check_no_namespace_init.sh` pre-commit hook guards against this.

## Development

```sh
uv sync                            # Install all workspace members in editable mode
uv run pytest                       # Run the full suite across every package
uv run pytest packages/oaknut-dfs/tests   # Run one package's tests
uv run ruff check                   # Lint
pre-commit run --all-files          # Run all hooks (ruff + namespace guard)
```

The workspace uses `[tool.uv.sources]` at the root so sibling deps like `oaknut-file` resolve to local paths during development, and to PyPI for end-user installs.

## Variable naming conventions

All packages follow these suffix conventions:

- `_filename` — just the name part (e.g. "HELLO")
- `_filepath` — full path to a file (e.g. `Path("/path/to/disc.ssd")`)
- `_dirpath` — a directory path
- `_dirname` — a directory name
- Avoid ambiguous `_file` or `_dir` suffixes.

## Commit messages

- Don't mention "Claude", Anthropic, or the underlying model.
- No emojis.
- Focus on the *why* of a change, not the *what*; the diff shows the what.
- Prefer many small, semantically-meaningful commits over one large batch during multi-step refactors.

## Prose conventions

- Use British "disc" rather than "disk" for Acorn-era subject matter. The project is about physical discs and the filing systems designed for them.

## Tooling

- Always use `uv` (not `pip` directly, not `poetry`).
- Do **not** commit any `uv.lock` file at any level — these are libraries, not applications, and committed lockfiles over-constrain end-user dependency resolvers.
- Dev dependencies live in `[dependency-groups]` at the workspace root (test, lint, dev). Per-package `pyproject.toml` files declare only their runtime dependencies.

## Test-first preference

When implementing a non-trivial change, write a failing test first, then make it pass. This applies equally to bug fixes and new features.

## Git safety

- Never `git push` without being asked. Leave pushes to the user.
- Never skip hooks (`--no-verify`).
- Don't run destructive operations (`git reset --hard`, `git clean -f`, `rm -rf` on version-controlled directories) without being asked.

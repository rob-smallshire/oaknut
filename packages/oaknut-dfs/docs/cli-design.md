# oaknut-dfs CLI — Design Document

**Status:** draft for iteration. Nothing here is decided — flag anything you want to change. Amend this file in place; commit history is the discussion log.

## Context

`oaknut-dfs` currently ships as a library only. The `pyproject.toml` entry point is commented out and there is no `cli.py`. The library's public API is substantial — DFS and ADFS images, catalogue/path operations, the `host_bridge` module with full `MetaFormat` coverage, and `basic.py` stubs for BBC BASIC tokenisation — and we now want a user-facing Click CLI that exposes all of it and feels consistent with `oaknut-zip`'s existing CLI.

The scope covers 25 operations: import/export (single file and bulk, with metadata), moving/renaming/copying within and between images (including DFS↔ADFS), cataloguing and tree display, metadata inspection and editing, attribute changes, image creation, deletion (files and empty directories), finding, wildcards, compaction, free-space reporting and visualisation, validation, Acorn path syntax, stdin/stdout streaming, boot option, and title management.

This document's job is to agree on **shape** before we build: naming conventions, command surface, TTY/output policy, error model, and which library gaps must be closed before which commands can ship.

## Prerequisite: monorepo migration

The CLI is intended to live in a dedicated `packages/oaknut-disc/` directory inside the planned `oaknut-*` monorepo. The monorepo migration described in `monorepo.md` is therefore a hard prerequisite for this work and lands first. Doing it in that order means:

- The CLI is born in its permanent home and never has to be relocated.
- `oaknut-disc` can declare path-dep development on its sibling library packages (`oaknut-file`, `oaknut-dfs`, eventually `oaknut-adfs` and `oaknut-basic`) via the `uv` workspace, with no PyPI publication round-trip during iteration.
- Cross-package fixes that surface during CLI work (e.g. a missing `glob()` on `DFSPath`) can be made and tested atomically in one commit alongside the consuming CLI code.
- The library splits (`oaknut-adfs` and `oaknut-basic` extracted from today's `oaknut-dfs`) become a downstream cleanup that the CLI inherits transparently — no CLI code change required when the splits happen.

Until the monorepo migration completes, this document is the agreed shape; no CLI code lands in `oaknut-dfs`.

---

## Guiding principles

1. **One binary, flat subcommand surface**, `git`-style. `disc <verb> <image> [args]`. No nested groups. (See "Binary name" below.)
2. **Consistent across DFS and ADFS.** The binary detects the format of the image on open and dispatches internally; users shouldn't have to know whether to reach for a DFS-specific or ADFS-specific command. Where operations are only meaningful for one format (e.g. `rmdir`, `mkdir`), the command errors cleanly on the other with a "not supported for DFS images" message.
3. **Mirror oaknut-zip's feel.** Click group, plain `click.echo` for scriptable output, Rich `Table` / `Tree` / `Panel` only where a human is clearly the audience (`ls`, `tree`, `info`, `freemap`). Lazy Rich imports inside the relevant commands so the fast-path commands don't pay for Rich startup.
4. **Pipe-friendly.** Every command that reads or writes file data accepts `-` as the host-side path to mean stdin/stdout. This is a single convention applied uniformly, not a per-command flag.
5. **Acorn-syntax paths in-image, host paths host-side.** In-image arguments look like `$.DIR.FILE`, `^.SIB`, `Games.Elite`, and are parsed by the in-image path machinery. Host-side paths are plain host paths. Ambiguity is resolved by position: the first arg after the image is always an in-image path; any `-o`/`-d`/`-i`/`--to` option is always a host path. See `cp` below for the cross-image case.
6. **Fail loudly, locally.** `click.ClickException` for user errors (exit 1 with "Error: " prefix), uncaught tracebacks only for genuine bugs, no swallow-and-log.

---

## Binary name and package home

The primary binary is **`disc`** — four characters, no `$PATH` clash on any Unix we're aware of, and the British "disc" spelling matches the project's prose convention for talking about Acorn-era discs.

`oaknut-disc` is registered as a secondary alias for disambiguation in case `disc` ever collides with a future system tool. Both names point at the same Click entry point, so users can type whichever they prefer:

```sh
disc ls foo.ssd
oaknut-disc ls foo.ssd
```

### Package layout

The CLI lives in a new `oaknut-disc` package created during the monorepo migration. The `oaknut-dfs` package today over-sells its name by handling both DFS *and* ADFS; the eventual library shape is:

| Package | Scope |
|---|---|
| `oaknut-file` | Shared metadata (already shipped) |
| `oaknut-dfs` | DFS / Watford DDFS / Opus DDOS only |
| `oaknut-adfs` | ADFS only (extracted from today's `oaknut-dfs`) |
| `oaknut-basic` | BBC BASIC tokeniser (extracted from today's `oaknut_dfs.basic`) |
| `oaknut-disc` | CLI only — depends on `oaknut-dfs`, `oaknut-adfs`, optionally `oaknut-zip` and `oaknut-basic` |

The library splits (`oaknut-adfs`, `oaknut-basic`) are a separate downstream refactor that happens *after* the CLI work, not before. While `oaknut-dfs` is still fat (containing the ADFS code), the CLI just depends on `oaknut-dfs` and uses both surfaces through its public API. When the splits happen later, `oaknut-disc`'s dependency list grows to add `oaknut-adfs` and `oaknut-basic`, and no CLI code changes.

---

## Command naming: Unix primary, star-prefixed Acorn aliases

Primary command names are Unix-flavoured (`ls`, `cat`, `rm`, `mv`, `cp`, `mkdir`, …) because that's the idiom every CLI user recognises and it composes naturally with standard pipelines. Alongside each Unix command we register an **Acorn alias prefixed with a literal `*`** that preserves the BBC Micro/Electron muscle memory: `*cat`, `*save`, `*load`, `*delete`, `*rename`, `*access`, `*title`, `*opt4`, …

This neatly resolves the `cat` conflict: `cat` keeps its Unix meaning ("dump file contents to stdout") and `*cat` is the Acorn-flavoured directory listing (which maps internally to the same implementation as `ls`). No name collisions, no shadowing, and the `*` prefix is a visual signal that you're invoking an Acorn-style command.

**Trade-off.** The `*` is a glob character in POSIX shells, so Acorn aliases must be escaped or quoted at the shell level. Three equivalent forms work in bash, zsh, dash, ksh, and fish:

```sh
disc \*cat foo.ssd          # backslash escape (lightest)
disc '*cat' foo.ssd          # single quotes
disc "*cat" foo.ssd          # double quotes — except see gotcha below
```

Gotchas:

- **Don't backslash-escape inside double quotes.** Inside `"…"` the backslash is *not* a generic escape — it's preserved literally for most characters including `*`. So `"\*cat"` sends `\*cat` (two characters) and the command rejects it. Either drop the backslash or switch to single quotes.
- **Windows is fine unquoted.** `cmd.exe` does not glob `*` itself, and PowerShell does not glob arguments to native executables, so `disc *cat foo.ssd` works as-is on Windows.

This is a minor but real usability tax on the Acorn aliases, and is the reason the Unix names are primary. Users who don't want to think about quoting always have `ls`, `get`, `put`, etc. available without fuss. We document the escaping forms in the CLI help and the README; users who type `disc *cat foo.ssd` unquoted on a POSIX shell will get a shell-expansion error that's clear enough once they've been told about it once.

**Click mechanics.** Click accepts arbitrary strings as subcommand names via `@cli.command(name="*cat")`. Registering multiple names per implementation can be done either by stacking command objects or by subclassing `click.Group` to support an `aliases=` keyword. The design doesn't depend on which mechanism we pick.

**Alias coverage.** Register an Acorn alias for every command that has a recognisable `*` form on the BBC Micro. Commands with no Acorn ancestor have no star alias — inventing one would be noise.

| Unix primary | Acorn alias | Origin                                            |
|--------------|-------------|---------------------------------------------------|
| `ls`         | `*cat`      | `*CAT`                                            |
| `cat`        | `*type`     | `*TYPE` (MOS command, displays file contents)     |
| `get`        | `*load`     | `*LOAD` (reads file data out of the filesystem)   |
| `put`        | `*save`     | `*SAVE` (writes file data into the filesystem)    |
| `rm`         | `*delete`   | `*DELETE`                                         |
| `mv`         | `*rename`   | `*RENAME`                                         |
| `cp`         | `*copy`     | `*COPY`                                           |
| `chmod`      | `*access`   | `*ACCESS`                                         |
| `mkdir`      | `*cdir`     | `*CDIR` (ADFS)                                    |
| `title`      | `*title`    | `*TITLE`                                          |
| `opt`        | `*opt4`     | `*OPT4,n`                                         |
| `stat`       | `*info`     | `*INFO FILENAME`.                                 |

The `stat` command is polymorphic: `stat IMAGE PATH` is the BBC `*INFO` equivalent; `stat IMAGE` with no path summarises the whole disc. `*info` accepts both forms.

Commands with no alias: `tree`, `find`, `validate`, `freemap`, `compact`, `create`, `export`, `import`, `setload`, `setexec`.

---

## Command surface

Grouped by category here for readability; actual `--help` output is a single flat list.

### Inspection

| Command | Purpose | Notes |
|---|---|---|
| `ls IMAGE [PATH]` (alias `*cat`) | List a directory catalogue as a Rich table | Default PATH is root |
| `tree IMAGE [PATH]` | Recursive Unicode box-drawing tree | Uses the same technique as `oaknut-zip`'s `_tree_display_names` |
| `stat IMAGE [PATH]` (alias `*info`) | Whole-disc summary when PATH is omitted (title, boot option, sector count, free space, file count, format detected — Rich panel). Single-file metadata when PATH is given (load, exec, length, attr, filetype — plain text, scriptable). | The two output styles are dispatched by the presence of PATH. |
| `freemap IMAGE` | Free-space map with ASCII fragmentation visualisation | ADFS: real regions; DFS: single trailing block |
| `validate IMAGE` | Run `DFS.validate()` / `ADFS.validate()`, report errors, exit 0 or 1 | |
| `find IMAGE PATTERN` | Glob files in-image by Acorn-style wildcard (`*` and `?`) | |
| `cat IMAGE PATH` (alias `*type`) | Dump file contents to stdout (Unix `cat`, MOS `*TYPE`) | Equivalent to `get IMAGE PATH -` |

### Moving file data

| Command | Purpose |
|---|---|
| `get IMAGE PATH [HOST_PATH]` (alias `*load`) | Export one file out, with metadata sidecar control. HOST_PATH defaults to the basename of PATH in CWD; `-` writes raw bytes to stdout (no sidecar). |
| `put IMAGE PATH [HOST_PATH]` (alias `*save`) | Import one file in. HOST_PATH `-` reads raw bytes from stdin (no sidecar lookup). |
| `export IMAGE HOST_DIR` | Bulk-export the whole image or a sub-tree into a host directory, with sidecars. |
| `import IMAGE HOST_DIR` | Bulk-import a host directory into the image (ADFS: recursive with mkdir; DFS: flat). |

### Modification

| Command | Purpose |
|---|---|
| `rm IMAGE PATH [PATH…]` (alias `*delete`) | Delete file(s). `-r` recursive directory delete (ADFS). `-f` force: ignore missing paths, override locked files. `--dry-run` print what would be removed and exit. |
| `mv IMAGE SRC DST` (alias `*rename`) | Rename / move within an image. `-f` overwrite an existing destination. |
| `cp IMAGE SRC DST` (alias `*copy`) | Copy within one image. `cp SRC_IMAGE SRC_PATH DST_IMAGE DST_PATH` for cross-image. `-f` overwrite an existing destination. |
| `mkdir IMAGE PATH` (alias `*cdir`) | Create a directory (ADFS only). `-p` no error if the directory already exists. |
| `chmod IMAGE PATH ACCESS` (alias `*access`) | Set access (e.g. `LWR/R` or hex `0x1B`). |
| `lock IMAGE PATH`, `unlock IMAGE PATH` | Convenience wrappers over `chmod`. |
| `setload IMAGE PATH ADDR`, `setexec IMAGE PATH ADDR` | Edit load / exec addresses in place. |
| `title IMAGE [NEW_TITLE]` (alias `*title`) | Read or set disc title. With `PATH` positional, reads/sets an ADFS directory title. |
| `opt IMAGE [0\|1\|2\|3]` (alias `*opt4`) | Read or set boot option (`*OPT4,x`). |

### Whole-image operations

| Command | Purpose |
|---|---|
| `create HOST_PATH --format ...` | Create a new empty disc image. Options: `--format ssd/dsd/adfs-s/adfs-m/adfs-l/adfs-hard --capacity N`. |
| `compact IMAGE` | Defragment. |

---

## Global conventions

### Argument ordering

Every command takes the image as its first positional argument. In-image paths follow. Host paths, where present, are explicit positional tails or `-o`/`-i` options depending on the command.

### Acorn path syntax

In-image path arguments accept:

- Absolute: `$`, `$.DIR.FILE`, `Games.Elite`
- Parent: `^` (one level up from current — we treat the image root as an implicit CSD so `^` at root is an error)
- CSD: `@` (equal to `$` at top level; meaningful only if we support `--cd` to set a CSD, which is deferred)

Library prerequisite: we need to add `^`/`@` parsing to the in-image path machinery, or have the CLI parse them and resolve to absolute before handing off to the library. Preference: the CLI does it — keeps the library path types pure — with a shared helper in `cli_paths.py`.

### Wildcards

Acorn convention: `*` matches any sequence within one name component, `?` matches one character. The CLI translates these to its own matcher and applies them to `iterdir`/`walk` output. Used by `find`, `rm`, `get` (when the argument is a wildcard) and `ls` (as a filter). Note that on the Acorn-alias `*delete PATTERN` form, the first `*` is the alias prefix, not a wildcard, so users will need to write e.g. `disc '*delete' foo.ssd '$.BACK*'` — the quoting tax again.

### Stdin / stdout via `-`

- `get IMAGE PATH -` → raw bytes of the in-image file on stdout (no sidecar, no metadata)
- `put IMAGE PATH -` → raw bytes from stdin written to the in-image file at PATH
- `cat IMAGE PATH` is equivalent to `get IMAGE PATH -`
- `get` / `put` with a dash always drop metadata (there's nowhere to put it). To round-trip metadata through a pipe, users can `export` to a tempdir and tar the result.

### TTY detection & `--plain`

Follow oaknut-zip's default: commands that emit Rich output (`ls`, `tree`, `info`, `stat`, `freemap`) use `Console()` which auto-detects TTY and strips ANSI when piped. Add one global `--plain` flag that forces plain output even at a TTY, for scripting. No `--no-color`; Rich already honours `NO_COLOR` via its standard logic.

### Error handling

All user-facing errors: `click.ClickException("…")`. Raised cleanly with no traceback on exit. Rare internal bugs: propagate naturally. No custom `sys.exit(N)` scattered through command bodies.

### Flag conventions

We follow standard Unix flag spellings so users don't have to learn a parallel vocabulary. Each flag has the same meaning everywhere it appears:

- `-f` / `--force` — Two-faced, both implied: (1) ignore missing inputs (`rm -f nonexistent` exits 0); (2) override Acorn locked-file protection (delete or overwrite a locked file without erroring). The CLI implements (2) by catching the lock error, calling `unlock`, and retrying — the library stays strict.
- `-r` / `--recursive` — Walk into directories. `rm -r DIR` is the obvious case; only meaningful on ADFS where directories nest.
- `-p` — `mkdir -p` only: don't error if the target directory already exists. (We do not support multi-level "create parents along the way" because Acorn directories don't nest more than one level at a time in any meaningful sense — you create one at a time.)
- `--dry-run` — Print what *would* happen and exit 0 without touching the image. Available on `rm`, `mv`, `cp`, `import`, `export`, `compact`. Particularly important for `rm -rf` and bulk import/export.
- `-v` / `--verbose` — Per-file echo to stderr (so it doesn't pollute stdout for piping). Available on bulk commands and on `cp` / `mv` / `rm` when wildcards expand.
- `-q` / `--quiet` — Suppress all non-error output. Mutually exclusive with `-v`.

### Metadata format option

Every command that exports or imports takes `--meta-format` with the same choices as oaknut-zip (`inf-trad`, `inf-pieb`, `xattr-acorn`, `xattr-pieb`, `filename-riscos`, `filename-mos`, `none`), defaulting to `inf-trad`. `--owner INT` for PiEB variants. No per-command divergence.

---

## Library prerequisites

From the API inventory, **11 of the 25 requirements are directly wrap-able today; 5 are partial; 9 are missing**. Before the CLI can cover the full surface, the library needs these additions. We'd add them smallest first, with each landing as its own commit so the CLI PR can stack cleanly on top.

| # | Addition | Size | Which CLI command needs it |
|---|---|---|---|
| L1 | Acorn wildcard matcher (`?` / `*`) as a small utility module | S | `find`, `rm PATTERN`, `ls PATTERN` |
| L2 | `DFSPath.glob(pattern)` / `ADFSPath.glob(pattern)` returning iterators | S | `find` |
| L3 | `DFSPath.copy(target)` / `ADFSPath.copy(target)` (within-image) | S | `cp` |
| L4 | `DFSPath.set_load_address(addr)` / `set_exec_address(addr)` — catalogue update without data rewrite | M | `setload`, `setexec` |
| L5 | `ADFSPath.set_load_address` / `set_exec_address` (same) | M | `setload`, `setexec` |
| L6 | `DFS.import_directory(host_dir)` / `ADFS.import_directory(host_dir)` — bulk importer mirroring `export_all` | M | `import` |
| L7 | Cross-format copy helper in `host_bridge` (or new module) that reads from one image and writes to another, mapping attributes best-effort | M | `cp` cross-image |
| L8 | Public `free_space_regions()` on both DFS and ADFS, returning `[(start_sector, length_sectors), …]`. DFS returns a single region; ADFS exposes the real map. | S | `freemap` |
| L9 | `ADFSPath.rmdir(recursive=True)` or a new `ADFSPath.rmtree()` for the `rm -r` case | M | `rm -r` |
| L10 | Parity check: ensure `ADFS.export_all` exists and matches the DFS surface | S | `export` |

**Not on the critical path** — we can ship v1 without them:

- Acorn `^` / `@` path operators: parse in the CLI for now, push into the library later.
- Recursive `DFSPath.walk()` to match ADFS's. DFS is flat so recursion is degenerate; the CLI `tree` command can special-case DFS and skip the walk.

**Deferred entirely:**

- Hard-disc DFS creation (DFS is floppy-only by format).
- Post-creation filename editing (already handled by `mv`).
- Cross-format copy with full attribute fidelity — we do best-effort mapping and document losses.

---

## Output / formatting details

### `ls`

Rich `Table` with columns: Name, Load, Exec, Length, Attr, Filetype (if stamped), Locked (marker). Dim styling on rows for locked files. Title row shows disc title + format + free space. When the target PATH doesn't exist, exit 1 with a clear error.

### `tree`

Unicode box-drawing tree using the same algorithm oaknut-zip uses in its `_tree_display_names` helper — compute sibling relationships, emit `├── / └── / │   /     ` prefixes. Works for ADFS natively; for DFS, the tree has one level (directory letters as children of root, files under each letter).

### `stat` (whole-disc form, no PATH)

Rich `Panel` with: title, cycle/format, boot option (named), total sectors, used sectors, free sectors (+ "fragmented into N regions" if ADFS), file count.

### `stat` (single-file form, with PATH)

Plain `click.echo` — multi-line key/value pairs, scriptable. No table, no rich. The output style is dispatched at runtime on the presence of PATH; both shapes share one Click command.

### `freemap`

ASCII row showing sector usage, something like:

```
Sectors: 0         100        200        300        400        500
         ##########....###..##########........................##....
                    ^^^^   ^^^^                                    ^^
Free: 272 sectors in 4 regions (largest 200 contiguous)
```

Legend: `#` = used, `.` = free. At narrow terminals we scale (multiple sectors per char); at wide terminals we go 1:1. Rich handles terminal width detection via `Console().size.width`.

### `validate`

Plain output: green "OK" line with file count if clean, red error list + non-zero exit if not.

### `find`

Plain output: one match per line, full Acorn path. Suitable for piping into `xargs`-style workflows.

---

## Entry point

The CLI lives in `packages/oaknut-disc/` inside the monorepo (see "Prerequisite: monorepo migration" above). All packages use PEP 420 namespace packaging under the shared `oaknut` import root, so the CLI's source lives at `packages/oaknut-disc/src/oaknut/disc/`. Its `pyproject.toml` declares both script entry points pointing at the same callable:

```toml
# packages/oaknut-disc/pyproject.toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "oaknut-disc"
requires-python = ">= 3.11"
dynamic = ["version"]
description = "CLI for working with Acorn DFS and ADFS disc images."
dependencies = [
    "oaknut-file>=1.0",
    "oaknut-dfs>=4.0",
    "click>=8.1.7",
    "rich>=13.0",
]

[project.scripts]
disc = "oaknut.disc.cli:cli"
oaknut-disc = "oaknut.disc.cli:cli"

[tool.setuptools.dynamic]
version = { attr = "oaknut.disc.__version__" }

[tool.setuptools.packages.find]
where = ["src"]
```

Source layout:

```
packages/oaknut-disc/
├── pyproject.toml
└── src/
    └── oaknut/                    # NAMESPACE — no __init__.py here
        └── disc/
            ├── __init__.py        # holds __version__
            ├── cli.py             # Click group + all subcommands
            └── cli_paths.py       # Acorn path parsing + wildcard matching
```

If `cli.py` grows unwieldy (> ~600 lines), split into `oaknut/disc/cli/` as a package with one module per command category.

`packages/oaknut-dfs/pyproject.toml` itself stays library-only — no script entry, no `cli.py`. When `oaknut-adfs` and `oaknut-basic` are eventually split out of `oaknut-dfs`, `oaknut-disc`'s `dependencies` list grows to include them; nothing else moves and no import statement at any call site changes (the namespace-package property guarantees that).

---

## Out of scope for v1

- Interactive REPL
- Disc image editor (hex)
- Image-to-image sync / rsync-like semantics
- Progress bars (plain `-v` echo is enough)
- Colour-blind / accessibility theming beyond Rich defaults
- Localisation
- A configuration file
- Tab completion scripts

All of those are reasonable future work but not where we want the first CLI to try to land.

---

## Open questions

Not blocking — just the spots where a decision will shape the final implementation sequence.

1. **`get` / `put` naming.** Are those the right Unix-primary names for single-file export/import? Alternatives: `extract`/`add` (matches oaknut-zip), `pull`/`push`, `read`/`write`. Star aliases are `*load`/`*save` either way.
2. **Cross-format `cp`.** Ship in v1 or defer? Adds test matrix weight (DFS→ADFS, ADFS→DFS, attribute mapping, locked-flag round-trip).
3. **`chmod` argument syntax.** Accept both symbolic (`LWR/PR`) and hex (`0x1B`), or just one? The library exposes both via `oaknut_file.format_access_text` / `format_access_hex`.
5. **`--plain` vs rely on Rich auto-detect alone.** Is the extra flag worth the surface area? oaknut-zip gets by without one.
6. **CSD (current directory) support.** Skip for v1, or wire it through a `--cd PATH` global option?
7. **Library prerequisite sequencing.** Land all 10 library additions first as a single prep commit, or interleave them with the CLI work command-by-command? Instinct: a single prep commit for L1–L10 then one CLI commit, so the CLI PR reads as a pure add.
8. **Alias registration mechanism.** `click.Group` subclass with an `aliases=` keyword, or multiple `@cli.command(name=...)` decorators pointing at the same implementation function? Either works; the second is more verbose but uses only stock Click.

---

## Verification (once the design is agreed)

Once this document is signed off we convert it into an implementation plan: ordered commits, test matrix per command (Click `CliRunner` + in-memory image fixtures), manual smoke-test script (`create` → `put` → `ls` → `get` → `validate` → `rm` → `compact` → `info`) that exercises the happy path end-to-end on both a DFS and an ADFS image.

# oaknut `disc` CLI — Design Document

**Status:** draft for iteration, updated 2026-04-12 to account for `oaknut-afs`. Nothing here is decided — flag anything you want to change. Amend this file in place; commit history is the discussion log.

## Context

The oaknut monorepo now ships library packages for three Acorn filesystem families:

- **DFS** (and variants: Watford DDFS, Opus DDOS) — flat-catalogue BBC/Electron floppies.
- **ADFS** — hierarchical directories, free space maps, hard-disc images.
- **AFS** — the Level 3 File Server's private on-disc format (`AFS0` magic), living in the tail cylinders of an old-map ADFS hard-disc image.

We want a unified `disc` CLI that exposes all three surfaces and feels consistent with `oaknut-zip`'s existing CLI.

The scope covers the original 25 DFS/ADFS operations plus AFS-specific operations: initialisation (the WFSINIT analogue), user management (passwords file), library merges, and transparent AFS-through-ADFS access where an ADFS disc carries an AFS partition. An interim standalone CLI (`oaknut-afs-disc`, shipped in phase 21 of the `oaknut-afs` build) already provides basic `info`/`ls`/`cat`/`put`/`initialise` subcommands for AFS; the unified `disc` tool subsumes it.

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
2. **Consistent across DFS, ADFS, and AFS.** The binary detects the format of the image on open and dispatches internally; users shouldn't have to know whether to reach for a format-specific command. Where operations are only meaningful for one format (e.g. `rmdir` on DFS, `afs-init` on a non-ADFS image), the command errors cleanly with a "not supported for … images" message. For ADFS images that carry an AFS tail partition, the `--afs` flag (or automatic detection via `ADFS.afs_partition`) lets commands reach into the AFS tree transparently — `disc ls image.dat --afs` lists the AFS root instead of the ADFS root.
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

The CLI lives in a new `oaknut-disc` package inside the monorepo. The monorepo migration and the library splits are done; the current shape is:

| Package | Scope |
|---|---|
| `oaknut-file` | Shared metadata, `host_bridge`, `Access`, `BootOption`, `FSError` base |
| `oaknut-discimage` | `Surface`, `SectorsView`, `UnifiedDisc` |
| `oaknut-basic` | BBC BASIC tokeniser/detokeniser |
| `oaknut-dfs` | DFS / Watford DDFS / Opus DDOS |
| `oaknut-adfs` | ADFS — hierarchical directories, free space maps, hard-disc images, `ADFS.afs_partition` |
| `oaknut-afs` | AFS — the Level 3 File Server's on-disc format. Read/write, `wfsinit` init/partition, merge, host-tree import, shipped library images. Ships an interim `oaknut-afs-disc` CLI entry point |
| `oaknut-zip` | ZIP archives containing Acorn files |
| `oaknut-disc` | **Unified CLI** — depends on all library packages; `oaknut-zip` optional |

`oaknut-afs` already ships `oaknut-afs-disc` as a standalone entry point with `info`/`ls`/`cat`/`put`/`initialise`. When the unified `disc` tool ships, it subsumes those subcommands and `oaknut-afs-disc` becomes an alias or is retired.

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
| `stat IMAGE [PATH]` (alias `*info`) | Whole-disc summary when PATH is omitted (title, boot option, sector count, free space, file count, format detected — Rich panel). With `afs:` prefix and no path, shows AFS disc name, geometry, start cylinder, free sectors, and user list. Single-file metadata when PATH is given (load, exec, length, attr, filetype — plain text, scriptable). | The two output styles are dispatched by the presence of PATH. |
| `freemap IMAGE` | Free-space map with ASCII fragmentation visualisation | ADFS: real regions; DFS: single trailing block; `freemap IMAGE --afs` or `freemap IMAGE afs:` shows per-cylinder AFS bitmap occupancy. |
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
| `create HOST_PATH --format ...` | Create a new empty disc image. Options: `--format ssd/dsd/adfs-s/adfs-m/adfs-l/adfs-hard --capacity N`. For hard-disc images that will carry AFS, follow `create` with `afs-init`. |
| `compact IMAGE` | Defragment (ADFS). AFS regions do not have a separate compaction step; `ADFS.compact()` moves ADFS data forward to free tail space for AFS. |

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

### Dual-partition addressing (ADFS + AFS)

A single hard-disc image (`.dat`/`.dsc`) can carry both an ADFS partition in its front cylinders and an AFS partition in its tail. The two share the same physical disc but expose different directory trees, different metadata models (ADFS has filetype stamping; AFS has user/quota), and different path rules (AFS names max 10 chars, no spaces).

The CLI resolves this using the **Acorn filing-system prefix convention**. On real Acorn hardware, paths were qualified by prefixing the filing system name — `ADFS::HardDisc4.$.Games`, `NET::Server.$.Library`. We adopt the same idiom with a `FS:` prefix on in-image paths:

```sh
disc ls scsi0.dat                        # default: ADFS root
disc ls scsi0.dat adfs:$                 # explicit: ADFS root
disc ls scsi0.dat afs:$                  # AFS root
disc ls scsi0.dat afs:$.Library          # AFS subdirectory
disc cat scsi0.dat afs:$.Library.Fs      # read a file from AFS
disc put scsi0.dat afs:$.NewFile src.bin # write into AFS
disc stat scsi0.dat afs:                 # AFS disc-level info (name, geometry, users)
```

The filing-system prefix is parsed by the CLI's `cli_paths.py` module before the path is handed to the library:

- **No prefix** → ADFS (for hard discs) or DFS (for floppies), auto-detected from image format. This is the common case and matches the existing DFS/ADFS design.
- **`adfs:`** → explicit ADFS. Useful for disambiguation when scripting.
- **`afs:`** → the AFS tail partition. The CLI opens the image as ADFS, calls `ADFS.afs_partition`, and operates on the resulting `AFS` handle. Errors cleanly if no AFS pointers are present.
- **`dfs:`** → explicit DFS (for the rare case where format detection is ambiguous).

The prefix is case-insensitive (`AFS:`, `afs:`, `Afs:` all work). The `::disc.` form from Acorn's multi-disc syntax is not needed — we have one image per command invocation — but could be added later if multi-image workflows arise.

**AFS-specific commands** that have no ADFS/DFS counterpart use the `afs-` prefix and always operate on the AFS partition:

| Command | Purpose |
|---|---|
| `afs-init IMAGE --disc-name NAME [--cylinders N] [--user NAME[:S]] …` | Partition + initialise an AFS region (wraps `wfsinit.initialise`). |
| `afs-users IMAGE` | List active users with quota, system flag, boot option. |
| `afs-useradd IMAGE NAME [--system] [--quota N] [--password PWD]` | Add a user to the passwords file. |
| `afs-userdel IMAGE NAME` | Remove a user (tombstone the slot). |
| `afs-merge IMAGE --source SOURCE_IMAGE [--target-path PATH]` | Merge a source AFS subtree into the target. |

These do not have Acorn star-aliases (the Level 3 File Server's admin interface was over Econet, not local `*` commands).

**Paths within the AFS partition** use `$.DIR.FILE` syntax with `.` as separator, just like ADFS. The 10-char / no-space name rules are enforced by `AFSPath` in the library. Users accustomed to ADFS paths will find AFS paths nearly identical.

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

The following additions are needed. Status updated 2026-04-12.

| # | Addition | Size | Status | Which CLI command needs it |
|---|---|---|---|---|
| L1 | Acorn wildcard matcher (`?` / `*`) as a small utility module | S | TODO | `find`, `rm PATTERN`, `ls PATTERN` |
| L2 | `DFSPath.glob(pattern)` / `ADFSPath.glob(pattern)` returning iterators | S | TODO | `find` |
| L3 | `DFSPath.copy(target)` / `ADFSPath.copy(target)` (within-image) | S | TODO | `cp` |
| L4 | `DFSPath.set_load_address(addr)` / `set_exec_address(addr)` — catalogue update without data rewrite | M | TODO | `setload`, `setexec` |
| L5 | `ADFSPath.set_load_address` / `set_exec_address` (same) | M | TODO | `setload`, `setexec` |
| L6 | `DFS.import_directory(host_dir)` / `ADFS.import_directory(host_dir)` — bulk importer mirroring `export_all` | M | TODO | `import` |
| L7 | Cross-format copy helper in `host_bridge` (or new module) that reads from one image and writes to another, mapping attributes best-effort | M | TODO | `cp` cross-image |
| L8 | Public `free_space_regions()` on both DFS and ADFS, returning `[(start_sector, length_sectors), …]`. DFS returns a single region; ADFS exposes the real map. | S | TODO | `freemap` |
| L9 | `ADFSPath.rmdir(recursive=True)` or a new `ADFSPath.rmtree()` for the `rm -r` case | M | TODO | `rm -r` |
| L10 | Parity check: ensure `ADFS.export_all` exists and matches the DFS surface | S | TODO | `export` |
| L11 | Filing-system prefix parser (`afs:`, `adfs:`, `dfs:`) in `cli_paths.py` — strips the prefix and returns a partition selector + bare path | S | TODO | all commands with dual-partition images |

**AFS library prerequisites — already landed:**

| # | Addition | Status |
|---|---|---|
| A1 | `AFS.from_file`, `ADFS.afs_partition` — read-path entry points | Done (phase 6) |
| A2 | `AFSPath.read_bytes`, `.write_bytes`, `.mkdir`, `.unlink`, `.iterdir`, `.stat` | Done (phases 6, 11-13) |
| A3 | `wfsinit.partition.plan` / `.apply` + `wfsinit.initialise` | Done (phases 15, 19) |
| A4 | `PasswordsFile` mutation surface (add / remove / quota / password / boot / system) | Done (phase 14) |
| A5 | `merge(target, source, ...)` AFS → AFS subtree copy | Done (phase 16) |
| A6 | `import_host_tree(target, source=, ...)` | Done (phase 18) |
| A7 | `LibraryImage` enum + shipped `.img` assets | Done (phases 17, follow-up 3) |
| A8 | Allocator with chain-expanding writes | Done (phases 8, follow-up 1) |
| A9 | Transactional flush (buffered `_write_sector`, commit/discard on exit) | Done (follow-up 2) |
| A10 | Quota enforcement (`_debit_quota` / `_credit_quota` on create/delete) | Done (follow-up 5) |

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
description = "CLI for working with Acorn DFS, ADFS, and AFS disc images."
dependencies = [
    "oaknut-file>=1.0",
    "oaknut-dfs>=4.0",
    "oaknut-adfs>=1.0",
    "oaknut-afs>=0.1",
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

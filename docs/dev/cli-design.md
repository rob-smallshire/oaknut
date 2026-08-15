# oaknut `disc` CLI — Design Document

**Status:** draft for iteration, updated 2026-04-12 to account for `oaknut-afs`. Nothing here is decided — flag anything you want to change. Amend this file in place; commit history is the discussion log.

## Context

The oaknut monorepo now ships library packages for three Acorn filesystem families:

- **DFS** (and variants: Watford DFS, Opus DDOS) — flat-catalogue BBC floppies.
- **ADFS** — hierarchical directories, free space maps, hard-disc images.
- **AFS** — the Level 3 File Server's private on-disc format (`AFS0` magic), living in the tail cylinders of an old-map ADFS hard-disc image.

We want a unified `disc` CLI that exposes all three surfaces and feels consistent with `oaknut-zip`'s existing CLI.

The scope covers the original 25 DFS/ADFS operations plus AFS-specific operations: initialisation (the WFSINIT analogue), user management (passwords file), library merges, and transparent AFS-through-ADFS access where an ADFS disc carries an AFS partition. (Historical note: phase 21 of the `oaknut-afs` build shipped a standalone `oaknut-afs-disc` CLI with basic `info`/`ls`/`cat`/`put`/`initialise` subcommands as a stopgap. The unified `disc` tool subsumed it and the stopgap has been retired.)

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
| `oaknut-exception` | `OaknutException` / `DataError` / `ConfigurationError` / `InternalError` hierarchy + `handled_errors` boundary helper |
| `oaknut-file` | Shared metadata, `host_bridge`, `Access`, `BootOption`, `FSError` base (a `DataError`) |
| `oaknut-discimage` | `Surface`, `SectorsView`, `UnifiedDisc` |
| `oaknut-basic` | BBC BASIC tokeniser/detokeniser |
| `oaknut-dfs` | DFS / Watford DDFS / Opus DDOS |
| `oaknut-adfs` | ADFS — hierarchical directories, free space maps, hard-disc images, `ADFS.afs_partition` |
| `oaknut-afs` | AFS — the Level 3 File Server's on-disc format. Read/write, `wfsinit` init/partition, merge, host-tree import, shipped library images |
| `oaknut-zip` | ZIP archives containing Acorn files |
| `oaknut-disc` | **Unified CLI** — depends on all library packages; `oaknut-zip` optional |

The standalone `oaknut-afs-disc` entry point that `oaknut-afs` shipped during the AFS build-out has been retired now that the unified `disc` tool is a strict functional superset (its `info` maps to `disc stat OUTER_PATH:afs:` + `disc afs-users`; the rest map one-for-one onto `disc ls`/`cat`/`put`/`afs-init`).

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

The `stat` command is polymorphic: `stat COMPOUND_PATH` with an INNER_PATH is the BBC `*INFO` equivalent; with the INNER_PATH omitted it summarises the whole disc. `*info` accepts both forms.

Commands with no alias: `tree`, `find`, `validate`, `freemap`, `compact`, `create`, `export`, `import`, `set-load`, `set-exec`.

---

## Command surface

Grouped by category here for readability; actual `--help` output is a single flat list.

Each command's first positional is a **`COMPOUND_PATH`** — an `OUTER_PATH:INNER_PATH` pair naming an image and an optional in-image path (see *Image and in-image path* below). `--help` shows it as `OUTER_PATH:INNER_PATH`; the tables below use `COMPOUND_PATH` for brevity. Where a command ignores the in-image part (`freemap`, `validate`, `compact`, …) the `OUTER_PATH` alone is the whole `COMPOUND_PATH`.

### Inspection

| Command | Purpose | Notes |
|---|---|---|
| `ls COMPOUND_PATH` (alias `*cat`) | List a directory catalogue as a Rich table | Default INNER_PATH is root |
| `tree COMPOUND_PATH` | Recursive Unicode box-drawing tree | Uses the same technique as `oaknut-zip`'s `_tree_display_names` |
| `stat COMPOUND_PATH` (alias `*info`) | Whole-disc summary when INNER_PATH is omitted (title, boot option, sector count, free space, file count, format detected — Rich panel). With an `afs:` selector and no path, shows AFS disc name, geometry, start cylinder, free sectors, and user list. Single-file metadata when INNER_PATH is given (load, exec, length, attr, filetype — plain text, scriptable). | The two output styles are dispatched by the presence of INNER_PATH. |
| `freemap COMPOUND_PATH` | Free-space map with ASCII fragmentation visualisation | ADFS: real regions; DFS: single trailing block; `--afs` or an `afs:` selector in the COMPOUND_PATH shows per-cylinder AFS bitmap occupancy. |
| `validate COMPOUND_PATH` | Run `DFS.validate()` / `ADFS.validate()`, report errors, exit 0 or 1 | |
| `find COMPOUND_PATH PATTERN` | Glob files in-image by Acorn-style wildcard (`*` and `?`) | |
| `cat COMPOUND_PATH` (alias `*type`) | Dump file contents to stdout (Unix `cat`, MOS `*TYPE`) | Equivalent to `get COMPOUND_PATH -` |

### Moving file data

| Command | Purpose |
|---|---|
| `get COMPOUND_PATH [HOST_PATH]` (alias `*load`) | Export one file out, with metadata sidecar control. HOST_PATH defaults to the basename of INNER_PATH in CWD; `-` writes raw bytes to stdout (no sidecar). |
| `put COMPOUND_PATH [HOST_PATH]` (alias `*save`) | Import one file in. HOST_PATH `-` reads raw bytes from stdin (no sidecar lookup). |
| `export COMPOUND_PATH HOST_DIR` | Bulk-export the whole image or a sub-tree into a host directory, with sidecars. |
| `import COMPOUND_PATH HOST_DIR` | Bulk-import a host directory into the image (ADFS: recursive with mkdir; DFS: flat). |

### Modification

| Command | Purpose |
|---|---|
| `rm COMPOUND_PATH [INNER_PATH…]` (alias `*delete`) | Delete file(s). The COMPOUND_PATH's INNER_PATH is the first to delete; extra positionals are additional bare INNER_PATHs in the same image and partition. `-r` recursive directory delete (ADFS). `-f` force: ignore missing paths, override locked files. `--dry-run` print what would be removed and exit. |
| `mv SRC DST` (alias `*rename`) | Rename / move within an image. `SRC` is a `COMPOUND_PATH`; `DST` is either a full `COMPOUND_PATH` naming the same OUTER_PATH or a bare `INNER_PATH` that inherits `SRC`'s image and partition. `-f` overwrite an existing destination. |
| `cp SRC DST` (alias `*copy`) | Copy a file or tree. `SRC` and `DST` are `COMPOUND_PATH`s: the same OUTER_PATH on both sides copies within an image, different OUTER_PATHs copy across them. `-r` recurse, `-f` overwrite an existing destination. |
| `mkdir COMPOUND_PATH` (alias `*cdir`) | Create a directory (ADFS only). `-p` no error if the directory already exists. |
| `chmod COMPOUND_PATH ACCESS` (alias `*access`) | Set access. Absolute (e.g. `LWR/R` or hex `0x1B`) replaces it; incremental (`+L`, `-W`, `+R/R`, `+L-W`) edits the current value. |
| `lock COMPOUND_PATH`, `unlock COMPOUND_PATH` | Convenience wrappers over `chmod`. |
| `set-load COMPOUND_PATH ADDR`, `set-exec COMPOUND_PATH ADDR` | Edit load / exec addresses in place. |
| `title COMPOUND_PATH [NEW_TITLE]` (alias `*title`) | Read or set disc title. With an INNER_PATH, reads/sets an ADFS directory title. |
| `opt COMPOUND_PATH [0\|1\|2\|3]` (alias `*opt4`) | Read or set boot option (`*OPT4,x`). |

### Whole-image operations

| Command | Purpose |
|---|---|
| `create HOST_PATH --format ...` | Create a new empty disc image. Options: `--format ssd/dsd/adfs-s/adfs-m/adfs-l/adfs-hard --capacity N`. For hard-disc images that will carry AFS, follow `create` with `afs-init`. |
| `compact COMPOUND_PATH` | Defragment (ADFS). AFS regions do not have a separate compaction step; `ADFS.compact()` moves ADFS data forward to free tail space for AFS. |

---

## Global conventions

### Argument ordering

Every command that addresses something inside an image takes a single fused `OUTER:INNER` **compound path** as its first positional. Host paths, where present, are explicit positional tails or `-o`/`-i` options depending on the command.

### Image and in-image path: the compound path

The image and the in-image path are joined by a colon:

```sh
disc ls hd.dat:$.Games          # image hd.dat, in-image path $.Games
disc ls hd.dat                  # whole image, no in-image path
```

Parsing lives in `parse_compound_path` in `cli_paths.py`. The rule is uniform:

- The split is at the *first* non-Windows-drive colon (`X:\…` drive letters are skipped). The portion to the left is the image and must exist as a file; if it does not, the error message quotes only that portion — so the user sees what was looked up without the noise of the in-image part.
- With no colon, the whole token is the bare image and the in-image path is empty; commands that require an in-image path report that themselves.

The filing-system prefix (`adfs:` / `afs:` / `dfs:`, see *Dual-partition addressing* below) sits on the in-image side of the outer image-colon. Because the outer split happens at the *first* non-Windows-drive colon, any subsequent colon — including the fs-prefix delimiter — stays in the in-image string, where `split_selector` (in `mount.py`) peels it off; `resolve_mount` then resolves the whole compound path to a mounted partition.

```sh
disc ls hd.dat:afs:$.Library    # image hd.dat, AFS partition, path $.Library
```

Commands with a positional *after* the path keep the compound path as their first argument and take the extra value as a trailing positional: `chmod COMPOUND_PATH ACCESS`, `set-load COMPOUND_PATH ADDR`, `get COMPOUND_PATH [HOST_PATH]`, `put COMPOUND_PATH [HOST_PATH]`.

Two commands take a second compound path:

- **`cp`** takes a source and a destination compound path: `cp src.dat:$.A dst.dat:$.B`. Naming different images copies across them; naming the same image on both sides copies within it.

- **`mv`** is single-image (at the library level) and takes a compound `SRC` plus a `DST`:
  - Fused, image repeated: `mv image.dat:$.A image.dat:$.B` — both tokens must name the same image; the CLI checks resolved paths and rejects the cross-image case.
  - Fused source, bare destination: `mv image.dat:$.A $.B` — `DST`'s image is redundant, so a bare in-image path inherits `SRC`'s image. A `DST` is treated as compound only when the text left of its outer colon names an existing file, so `adfs:$.B` stays a bare (selector-prefixed) in-image path. A destination partition selector must match the source's; mv never moves across partitions.

`rm` is multi-path: `rm COMPOUND_PATH [INNER_PATH...]` — the COMPOUND_PATH's in-image part is the first to delete and any extra positionals are additional bare INNER_PATHs in the same image and partition.

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

**Mismatch errors.** The prefix is a hard assertion, not a hint. If the image format doesn't match the prefix, the command refuses immediately with a specific diagnostic:

- `dfs:` on an ADFS image → `"image is ADFS format; cannot access as DFS"`
- `adfs:` on a `.ssd` DFS floppy → `"image is DFS format; cannot access as ADFS"`
- `afs:` on a disc with no AFS pointers → `"no AFS partition found on this disc"`
- `adfs:` on a disc that has AFS — fine, operates on the ADFS front partition as requested

**AFS-specific commands** that have no ADFS/DFS counterpart use the `afs-` prefix and always operate on the AFS partition:

| Command | Purpose |
|---|---|
| `afs-init IMAGE --disc-name NAME [--cylinders N] [--user NAME[:S][:QUOTA]] [--user-password NAME=PWD] …` | Partition + initialise an AFS region (wraps `wfsinit.initialise`). |
| `afs-users IMAGE` | List active users with quota, system flag, boot option. |
| `afs-useradd IMAGE NAME [--system] [--quota N] [--password PWD]` | Add a user to the passwords file. |
| `afs-userdel IMAGE NAME` | Remove a user (tombstone the slot). |
| `afs-passwd IMAGE NAME --password PWD` | Change an existing user's password (in-place, never grows the file). |
| `afs-merge IMAGE --source SOURCE_IMAGE [--target-path PATH]` | Merge a source AFS subtree into the target. |

These do not have Acorn star-aliases (the Level 3 File Server's admin interface was over Econet, not local `*` commands).

**Passwords are cleartext.** The Level 3 File Server stores each password as up to six plain ASCII bytes (`PWPASS`/`MAXPW`) in the `$.Passwords` file; there is no encryption. The only thing hiding them on a real disc is the `&00` access byte on the passwords file. Because a password sits inside an otherwise colon-delimited `--user` spec awkwardly — a password may itself contain `:` — `afs-init` keeps the password out of the `--user` grammar entirely. Passwords are passed through a separate `--user-password NAME=VALUE` option, split **once** on the first `=`, so the value after it is taken verbatim. `NAME` must match a `--user` or a built-in (`Syst`, `Boot`, `Welcome`); a built-in needs no matching `--user` to take a password.

**Paths within the AFS partition** use `$.DIR.FILE` syntax with `.` as separator, just like ADFS. The 10-char / no-space name rules are enforced by `AFSPath` in the library. Users accustomed to ADFS paths will find AFS paths nearly identical.

### Drive addressing within a DFS partition (double-sided discs)

The filing-system prefix above selects a *partition*. Inside the DFS family there is a second, finer axis: a double-sided floppy (`.dsd`) is **two independent DFS volumes** — Acorn drives `:0` and `:2` — not one volume spanning both surfaces (unlike ADFS-L, which is a single logical volume across both physical sides). The drive is addressed with **verbatim Acorn path syntax**: the in-partition path may carry a leading `:drive.` prefix, which the DFS filesystem itself parses.

```sh
disc cp "drive-0.ssd:*" elite.dsd            # bare path → drive 0 (the default)
disc cp "drive-2.ssd:*" elite.dsd::2.$        # drive 2 (the second side)
disc ls   elite.dsd::2.$
disc cat  elite.dsd::2.Z.MYDATA
disc stat elite.dsd                           # lists both sides: Drive :0, Drive :2
```

The compound form has two colons because the first is the CLI's image delimiter and the second is the DFS drive colon, preserved verbatim. An unqualified path is always drive 0 (there is no stateful "current drive"). Drive input is forgiving — `:0` is the first side and any non-zero drive is the second — but the canonical designation shown by `stat` is the Acorn-faithful `:0` / `:2`. On a length-ambiguous image (the 80T-SS / 40T-DS byte collision) an explicit non-zero drive *implies* the double-sided reading, overridden by an explicit `--geometry`; addressing a side that is not there fails cleanly, named by its designation. The mechanism is the filesystem-owned `split_volume` / `volumes` / `open(surface=)` contract — see `dsd-side-addressing.md`.

### Wildcards

Acorn convention: `*` matches any sequence within one name component, `?` matches one character. The CLI translates these to its own matcher and applies them to `iterdir`/`walk` output. Used by `find`, `rm`, `get` (when the argument is a wildcard) and `ls` (as a filter). Note that on the Acorn-alias `*delete PATTERN` form, the first `*` is the alias prefix, not a wildcard, so users will need to write e.g. `disc '*delete' foo.ssd '$.BACK*'` — the quoting tax again.

### Stdin / stdout via `-`

- `get COMPOUND_PATH -` → raw bytes of the in-image file on stdout (no sidecar, no metadata)
- `put COMPOUND_PATH -` → raw bytes from stdin written to the in-image file at INNER_PATH
- `cat COMPOUND_PATH` is equivalent to `get COMPOUND_PATH -`
- `get` / `put` with a dash always drop metadata (there's nowhere to put it). To round-trip metadata through a pipe, users can `export` to a tempdir and tar the result.

### TTY detection & `--plain`

Follow oaknut-zip's default: commands that emit Rich output (`ls`, `tree`, `info`, `stat`, `freemap`) use `Console()` which auto-detects TTY and strips ANSI when piped. Add one global `--plain` flag that forces plain output even at a TTY, for scripting. No `--no-color`; Rich already honours `NO_COLOR` via its standard logic.

### Environment variables

**Naming convention (pinned).** oaknut's own environment variables are `OAKNUT_<TOOL>_<SETTING>` — upper-case, underscore-separated, scoped to the reading tool (`DISC` for the `disc` CLI, leaving room for a future `OAKNUT_ZIP_…` etc.). Each such variable is the default for an explicit flag of the same meaning, so the flag can override it per invocation and the two never drift; wire it with Click's per-option `envvar=`, **not** `auto_envvar_prefix` (which would bake the *subcommand* into the name and so give `ls` and `stat` different variables for one setting). Standard cross-tool variables (`NO_COLOR`, `CLICOLOR`) are honoured **unprefixed** — renaming them would defeat the point.

The live list lives in the user docs at `docs/disc/cli/conventions/environment.rst`; keep it in step when adding a variable. As of writing: `OAKNUT_DISC_RAW_ADDRESSES` (oaknut-owned), plus `NO_COLOR` / `CLICOLOR` (external).

### Error handling

The contract has two halves:

1. **Domain failures produce a clean one-line diagnostic on stderr and a non-zero exit code.** A directory full, a disc full, a locked file, an invalid filename, a malformed image — none of these should ever surface as a Python traceback. They are expected runtime conditions the user (or their shell script) is meant to react to.

2. **Programming errors produce a traceback.** `KeyError`, `TypeError`, `AttributeError`, `ValueError` and other builtin exceptions signal that *the code is broken* — the wrong argument shape, an internal invariant violation, a key the developer thought always existed. The CLI must not catch and prettify these; the traceback is the bug report.

The split is enforced by `oaknut-exception`:

- **Library layer:** Every expected runtime failure raises a subclass of `oaknut.file.exceptions.FSError`, which itself inherits from `oaknut.exception.DataError`. Each subclass carries its own `_exit_code` class attribute (a `sysexits.h` value from the `ExitCode` enum), so `exc.exit_code` is the truth — no separate mapping table. For one-off cases where a subclass doesn't fit, the constructor accepts an `exit_code=` keyword override: `raise FSError("path not found: $.X", exit_code=ExitCode.OS_FILE)`. If a library function naturally wants to raise `ValueError`/`KeyError`/`FileNotFoundError` for user-supplied input, that raise is wrong — convert it to a `DataError` subclass at the input boundary so every caller (CLI, library client, tests) can match on category.

- **CLI layer:** The `AliasGroup.invoke()` method wraps every subcommand in `oaknut.exception.handled_errors`. The boundary catches `DataError` and `ConfigurationError` (and any `ExceptionGroup` of them), walks each leaf's `__cause__` chain and `__notes__` via `render_error`, prints to stderr via the `oaknut.disc.console.print_error` helper, and exits with the first leaf's `exit_code`. `InternalError` (and any non-OaknutException) propagates — its traceback is the report-an-issue signal. There is no per-command decorator and no per-class lookup table.

A group-level `--debug` flag re-raises `DataError`/`ConfigurationError` after printing so a developer sees the full traceback during iteration; users leave it off.

Scripts MAY branch on the following exit codes. They are stable across the lifetime of the CLI and follow the BSD `sysexits.h` set (codes 0 and 64–78), exposed by the `exit-codes` package as `ExitCode`:

| Code | `ExitCode`     | Category | Mapped from |
|---|---|---|---|
| 0   | `OK`           | Success | — |
| 2   | —              | Click usage error | Bad flags, missing arguments (emitted by Click before `handled_errors` runs) |
| 64  | `USAGE`        | Bad input shape | `AFSInitSpecError` and subclasses (disc name, user name, password, quota) |
| 65  | `DATA_ERR`     | Invalid data on disc | `CatalogReadError`, `InvalidFormatError`, `ADFSDirectoryError`, `ADFSMapError`, `AFSFormatError` and subclasses, `AFSRepartitionError` and subclasses, `AFSMergeConflictError`. Fallback for any uncategorised `DataError`. |
| 70  | `SOFTWARE`     | Internal failure | `InternalError` propagates with a traceback; this is what an uncategorised non-Oaknut exception is reported as if it ever reaches our handler. |
| 72  | `OS_FILE`      | Path not found | `ADFSPathError`, `AFSPathError`, `AFSDirectoryEntryNotFoundError`, `AFSUserNotFoundError`, CLI-side "path not found" pre-checks |
| 73  | `CANT_CREATE`  | Cannot create entry | Already exists, directory full, disc full, quota exceeded, directory not empty: `CatalogFullError`, `DiscFullError`, `FileExistsError`, `ADFSDirectoryFullError`, `ADFSDiscFullError`, `ADFSEntryExistsError`, `ADFSDirectoryNotEmptyError`, `AFSDirectoryFullError`, `AFSDirectoryEntryExistsError`, `AFSDirectoryNotEmptyError`, `AFSInsufficientSpaceError`, `AFSQuotaExceededError`, `AFSUserExistsError` |
| 74  | `IO_ERR`       | Host-side I/O | `AFSHostImportError` |
| 77  | `NO_PERM`      | Locked / access denied | `FileLocked`, `ADFSFileLockedError`, `AFSFileLockedError`, `AFSAccessDeniedError` |
| 78  | `CONFIG`       | Runtime environment | `ConfigurationError`. Not commonly used by `disc` itself; reserved for programs built on the library. |

The mapping lives on the exception classes themselves: each subclass declares its own `_exit_code`. New exception classes get a code by setting that attribute, not by editing a central table.

### Testing the contract

Every command must have at least one test that exercises a realistic failure mode and asserts the result is *clean* (no traceback) with the *right* exit code. The shared helper `assert_clean_error` in `packages/oaknut-disc/tests/test_cli_error_reporting.py` enforces three invariants on every failure result:

1. `result.exception` is `None` or `SystemExit` — anything else means an exception leaked out of the command and would have produced a traceback under a real shell. (Click's `CliRunner` captures uncaught exceptions on `result.exception` rather than writing a traceback to `result.output`, so the "no Traceback" string check that works in subprocess tests is misleading here.)
2. `result.exit_code` matches the expected category.
3. The rendered message contains an expected substring (case-insensitive).

When a new test surfaces a leaked `ValueError`/`KeyError`/etc., the fix belongs in the library — convert the raise to an `FSError` subclass — not in the CLI catch list.

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
| L4 | `DFSPath.set_load_address(addr)` / `set_exec_address(addr)` — catalogue update without data rewrite | M | TODO | `set-load`, `set-exec` |
| L5 | `ADFSPath.set_load_address` / `set_exec_address` (same) | M | TODO | `set-load`, `set-exec` |
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
| A7 | `LibraryImage` enum + shipped `.adl` assets | Done (phases 17, follow-up 3) |
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

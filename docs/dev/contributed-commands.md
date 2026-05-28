# Filesystem-contributed CLI commands — design

**Status:** DRAFT for discussion (not yet implemented). Phase E of the
filesystem-extensibility work (see `filesystem-extensions.md` and
`filesystem-extensions-phase-c.md`). Capturing the target before writing
code.

## 1. Why this doc

Every *generic* `disc` command — those that open an existing partition
and operate through the capability contract (`ls`, `tree`, `cat`, `put`,
`rm`, `stat`, …) — has been migrated onto the content-first mount
substrate, and the CLI no longer branches on filesystem type for any of
them. What remains in `oaknut-disc/cli.py` is a different *kind* of
command:

| Command | Owner | What it does |
|---|---|---|
| `generate-dsc` | ADFS | Synthesise a `.dsc` hard-disc geometry sidecar |
| `expand` | DFS | Pad a truncated `.ssd`/`.dsd` to its format size |
| `afs-init` / `afs-plan` / `afs-users` / `afs-useradd` / `afs-userdel` / `afs-passwd` / `afs-merge` | AFS | Partition, initialise, and administer the AFS region inside an ADFS disc |

These don't fit the generic Mount model: they **create** images, write
**format-specific sidecars**, or administer **one filesystem's private
structures** (AFS users, passwords, partitioning). They are inherently
tied to a single format — and they are the only remaining code in
`oaknut-disc` that imports `oaknut.dfs` / `oaknut.adfs` / `oaknut.afs`
directly.

The goal: let a *filesystem package contribute its own admin
subcommands* to the `disc` CLI, so the command lives with the code it
drives, and `oaknut-disc` carries neither the command bodies nor the
filesystem imports.

## 2. Decisions (settled in discussion)

1. **A shared `oaknut-cli` utility package** holds the CLI primitives
   both `oaknut-disc` and the contributing filesystem packages need. It
   sits *below* the filesystem packages, which is what breaks the
   dependency cycle (see §4).
2. **Filesystem packages stay import-pure by default.** Each grows an
   optional **`[cli]` extra** (Click + asyoulikeit + `oaknut-cli`) and a
   thin `cli` submodule; a non-CLI consumer of `oaknut-afs` never pulls
   Click.
3. **Contributed commands are grouped, not flat** — `disc afs init`,
   `disc adfs generate-dsc`, `disc dfs expand`. A package contributes one
   Click *group* named for its filesystem. Grouping namespaces the
   commands, so two filesystems can each contribute (say) a
   `generate-dsc` without a flat-name collision, and `disc afs --help`
   self-documents the family.

## 3. The `oaknut.command` axis

A new entry-point namespace, **`oaknut.command`**, mirroring the
`oaknut.filesystem` axis but simpler: where a filesystem entry point
yields a `Filesystem` *class*, a command entry point yields a ready-made
Click `Group` (or `Command`) *object*.

```toml
# packages/oaknut-afs/pyproject.toml
[project.entry-points."oaknut.command"]
afs = "oaknut.afs.cli:afs"        # afs is a click.Group
```

The `disc` root group, once defined, discovers every registered command
and attaches it:

```python
# oaknut-disc/cli.py, after `cli` is defined
from oaknut.cli import contributed_commands

for command in contributed_commands():   # stevedore over "oaknut.command"
    cli.add_command(command)
```

`contributed_commands()` lives in `oaknut-cli` and loads the
`oaknut.command` namespace through stevedore (the same machinery
`oaknut.filesystem` uses, with `load_failure_callback`), returning the
Click objects. An install sees exactly the commands its installed
filesystems contribute — the same true-extensibility property the
filesystem axis has.

**The error boundary is inherited for free.** `AliasGroup.invoke`
already wraps the *whole* dispatch in `oaknut.exception.handled_errors`,
and Click threads a nested group's invocation through the root group's
`invoke`. So `disc afs init` runs inside the same `handled_errors`
context as `disc ls` — a contributed command needs no per-command error
handling, and gets `--debug` re-raising and categorised exit codes
automatically. Contributed groups are therefore plain `click.Group`s;
they need none of `AliasGroup`'s machinery (the Acorn star-aliases like
`*CAT` belong to the generic commands and stay in `oaknut-disc`).

## 4. Breaking the dependency cycle

`oaknut-disc` depends on `oaknut-afs` (batteries-included: `pip install
oaknut-disc` works with every filesystem). So a command living in
`oaknut-afs` must **not** import `oaknut-disc`. The helpers the `afs-*`
commands use today split cleanly by where they belong:

- **AFS-access helpers** — `_open_afs`, `open_image_for_afs_write`,
  `_navigate_afs`, `_adfs_from_file` — aren't "disc" logic at all; they
  are thin wrappers over the public `oaknut.adfs`/`oaknut.afs` API. They
  move *into* `oaknut.afs.cli` (or the AFS library), where importing AFS
  is natural.
- **AFS-specific report/parse helpers** — `_build_afs_plan_reports`,
  `_parse_user_specs`, `_apply_user_passwords` — travel with the
  commands into `oaknut.afs.cli`.
- **Generic CLI primitives** — `report_output` (already `asyoulikeit`),
  `handled_errors` (already `oaknut.exception`), and the report cells
  `kv_table` / `size_cell` / `address_cell` — need a home *below* the
  filesystem packages. That home is **`oaknut-cli`**.

The resulting layering (a new package, no cycle):

```
            oaknut-cli
   (click, asyoulikeit, oaknut-exception,
    oaknut-file, oaknut-filesystem)
   • oaknut.command discovery: contributed_commands()
   • report cells: kv_table / size_cell / address_cell
        ^                              ^
        |                              |
  oaknut-afs[cli]                 oaknut-disc
   → oaknut.afs.cli:afs            • defines the root AliasGroup
   • afs group + entry point       • generic commands (mount substrate)
   • AFS-access + report helpers   • attaches contributed_commands()
```

`oaknut-disc` depends on `oaknut-cli` and on `oaknut-{dfs,adfs,afs}[cli]`
(the extra pulls Click + asyoulikeit + `oaknut-cli`). `oaknut-afs[cli]`
depends on `oaknut-cli`. Because `oaknut-cli` is strictly below the
filesystem packages, nothing points back up — the cycle is gone.

`resolve_mount` / COMPOUND_PATH parsing stay in `oaknut-disc`: the
contributed admin commands take a plain image path (`click.Path`), not a
partition-addressing COMPOUND_PATH, so they don't need the mount substrate.

## 5. What moves where

| Command(s) | New home | Contributed group | Notes |
|---|---|---|---|
| `expand` | `oaknut.dfs.cli` | `disc dfs expand` | zero `oaknut-disc` deps today |
| `generate-dsc` | `oaknut.adfs.cli` | `disc adfs generate-dsc` | zero `oaknut-disc` deps today |
| `afs-init`, `afs-plan`, `afs-users`, `afs-useradd`, `afs-userdel`, `afs-passwd`, `afs-merge` | `oaknut.afs.cli` | `disc afs init` / `plan` / `users` / … | brings its AFS-access + report/parse helpers |

Promoted into `oaknut-cli` (public, no longer underscore-private):
`kv_table`, `size_cell`, `address_cell` — used by the contributed
commands *and* by `oaknut-disc`'s own `stat` (which imports them from the
kit afterwards).

### Naming note: `disc afs` the command vs `afs:` the selector

`disc afs init` (a subcommand) is distinct from the `afs:` partition
selector inside a COMPOUND_PATH argument (`disc ls image:afs:`). One is a
command name in the argv command position; the other is part of an
argument value parsed by `split_selector`. They never occupy the same
grammatical slot, so there is no ambiguity.

## 6. Documentation & coverage impact

`scripts/check_doc_coverage.py commands` asserts every `disc` subcommand
has an `.. oaknut-command::` entry plus a `cli-example` recipe. Two
consequences:

- The check enumerates the live CLI, so it must descend into contributed
  *groups* (`afs init`, not just `afs`). The doc directives and the
  `scripts/cli-examples/*.py` recipes shift from `afs-init` to
  `afs init`, etc.
- Coverage now spans packages: a contributed command's docs still live
  under `docs/disc/`, but its *code* lives in the filesystem package.

## 7. Migration plan

Incremental, each step green and committed:

1. **Create `oaknut-cli`.** Move the report cells in (promote from
   `_`-private), add `contributed_commands()` + the `oaknut.command`
   namespace constant. Point `oaknut-disc`'s `stat` at the kit's cells.
   Have `cli.py` attach `contributed_commands()` (a no-op until something
   registers).
2. **`oaknut-dfs[cli]` → `disc dfs expand`.** Smallest move (no shared
   helpers); proves the axis end-to-end. Delete `expand` from
   `oaknut-disc`.
3. **`oaknut-adfs[cli]` → `disc adfs generate-dsc`.** Likewise.
4. **`oaknut-afs[cli]` → the `afs` group.** The largest: move the seven
   commands plus their AFS-access, report, and parse helpers. Delete from
   `oaknut-disc`, dropping its last direct `oaknut.afs` import.
5. **Docs + examples.** Rework `docs/disc/` entries and cli-examples to
   the grouped form; extend the coverage check to walk nested groups.
6. **Cleanup.** With the admin commands gone, `oaknut-disc` imports no
   filesystem package — verify the extensibility invariant
   (`grep -E "from oaknut\.(dfs|adfs|afs)" oaknut/disc/` empty) and retire
   any now-dead `cli_paths.py` remnants.

## 8. Non-goals

- Not reworking the generic commands or `resolve_mount` — they stay in
  `oaknut-disc`.
- Not a general plugin-permission/sandbox model — `oaknut.command` is
  trusted code from installed packages, exactly like `oaknut.filesystem`.
- Not changing `create` — it already routes through the registry
  (`creating_filesystem` + `Filesystem.create`); it stays a generic
  `oaknut-disc` command.

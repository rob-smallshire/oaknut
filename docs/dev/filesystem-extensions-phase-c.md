# Phase C tracking — rewire the disc CLI onto the filesystem contract

Working checklist for the Phase C migration (see
`filesystem-extensions-plan.md`). Commit command-by-command; tick items
as they move onto the `oaknut.filesystem` coordinator + capability
dispatch, with `FilingSystem`/direct-class use removed.

**Invariant being established:** `oaknut-disc` imports no filesystem
package and branches on none. Dependencies stay (batteries-included);
the *code* decouples. Done when `grep -E "FilingSystem|from oaknut\.(dfs|adfs|afs)"`
in `oaknut/disc/` is empty (bar the kept pyproject deps).

## Substrate

- [x] `mount.py` — `resolve_mount(FILE_SPEC, --filesystem, --geometry)`
  → mounted partition + in-partition path, via the coordinator.
- [x] partition-selector addressing (`<fs>[.index]:`), replacing
  `FilingSystem`/`parse_prefix`/`detect_filing_system`/`open_image`/`_navigate`.
- [x] `--filesystem` / `--geometry` shared options.

## Introspection / meta

- [ ] `identify` — re-point to `oaknut.filesystem.identify` (new result shape).
- [ ] `list-formats` → `list-filesystems`; `describe-format` → `describe-filesystem`.
- ( `list-report-formats` / `describe-report-format` / `list-reports` /
  `describe-report` are asyoulikeit output-format commands — out of scope. )

## ✓ Resolved — geometry-aware recursion

Discovered migrating `ls`: recursion handed the tail filesystem a
**raw-byte window**, correct only for *linear* geometries. On an
**interleaved** disc (ADFS-L, DFS `.dsd`) the tail's logical sectors are
scattered through the byte stream. **Fixed** (commit "Make region
recursion geometry-aware"): reserved regions are logical-sector runs
(`Partition.start_sector`/`num_sectors`); `region_reader(reader,
geometry, start, count)` gives a cheap byte window when the host is
linear and a de-interleaved `UnifiedDisc` view when it is a floppy. ADFS
reports its reserved tail via the &F6 pointer; the AFS mount root
`exists`/`stat` is fixed. Verified end-to-end through the CLI by
`test_ls_afs_prefix` on an ADFS-L+AFS floppy fixture.

## Read commands (core + capability-gated)

- [x] `ls` — on the substrate; capability dispatch (Titled/FreeSpace/
  AcornMetadata); DFS nameless-root model; works DFS/ADFS/AFS incl.
  AFS-on-interleaved-floppy.
- [x] `tree` — whole-image tree from `partition_selectors()` + generic
  `Mount.iter_entries`; partitions labelled by selector.
- [x] `cat` — `Mount.read_bytes`.
- [x] `type` — `Mount.read_bytes` + line-ending translation.
- [x] `find` — all-partition / prefix-scoped walk via `partition_selectors`.
- [x] `get` — `Mount.read_bytes` + `AcornMetadata.acorn_meta`.
- [x] `export` — host-partition tree export via `Mount.iter_entries`.
- [x] `get-load` / `get-exec` — gated on `AcornMetadata` (`_require_acorn_meta`).

### Structural commands — migrated

- [x] `validate` — `Validatable` capability (DFS/ADFS opt-in; AFS clean).
- [x] `freemap` — geometry-free `FreeMap`/`FreeMapData`; one terminal-sized
  sector matrix (per user steer, AFS shading dropped).
- [x] `stat` — navigates the partition structure; `Sized` +
  `PhysicalGeometry` capabilities; hard-disc CHS resolved from the `.dsc`
  sidecar via `geometry_from_dsc` (geometry on `Geometry`; identification
  stays content-first).

## ✓ Resolved — write-back path (substrate done)

The mutating commands needed the mount to *persist*. Chosen approach
(user steer): a **writable file-backed reader**, no flush ceremony.

- [x] Writable `ImageReader`: `reader_for(..., writable=True)` maps the
  file `ACCESS_WRITE`; `write()` and a live `buffer()` reach the file;
  windows inherit writability. Read-only `buffer()` is a private copy.
- [x] DFS/ADFS adapters build over `reader.buffer()` — writes persist
  when writable (verified by reopen-and-read tests); interleaved ADFS-L
  scatters back through the class's own `UnifiedDisc`.
- [x] AFS-region write-back on a **linear** host (hard disc): the region
  is a writable window; AFS builds over `buffer()` and flushes after
  each mutation. Interleaved-floppy AFS *writes* are refused with a clear
  message (the de-interleaved copy can't scatter back live) — reads are
  unaffected.
- [x] `resolve_mount(spec, writable=True)` opens writable and returns a
  context-managed `ResolvedMount` that owns the live mapping (released on
  exit); read-only mounts close at once.

### Write / mutate commands — migrated

Capability additions made: `set_acorn_meta` un-stubbed (keystone — DFS
lock-bit only, ADFS/AFS full); `remove`/`rename` on the Mount core;
richer `make_directory` (parents/exist_ok/title); `Mount.join`; `Titled.
set_title`, `Bootable.set_boot_option`, and a new `DirectoryTitled`
capability. A mount-based wildcard/recursive target iterator
(`_iter_target_paths`) and a shared `_mutate_access` helper back the
metadata commands. Access turned out wire-canonical at the mount
boundary (AFS exposes a translated wire `Access`; its `chmod` maps wire
back to AFS bits), so no separate access-representation layer was needed.

- [x] `put`  (`write_bytes` + `set_acorn_meta`)
- [x] `import`  (bulk; reuses `make_directory` / `join`)
- [x] `set-load` / `set-exec`
- [x] `chmod`, `lock` / `unlock`  (wire `Access` via `_mutate_access`)
- [x] `rm` / `mv`  (`remove(force=)` / `rename`)
- [x] `mkdir`  (gated on `HierarchicalDirectories`)
- [x] `title`  (`Titled` / `DirectoryTitled`)
- [x] `opt`    (`Bootable`)
- [ ] `cp`  (cross-image copy: read mount → write mount)
- [ ] `compact` / `expand`  (filesystem-specific admin; likely Phase E)

## Creation / format-specific admin (likely deferred to Phase E)

These don't fit the generic Mount model — creation needs (filesystem,
geometry); the AFS-* commands are filesystem-specific administration.
Candidates for a future "filesystem-contributed command" axis.

- [ ] `create`  (rework around `--filesystem` + `--geometry`)
- [ ] `generate-dsc`  (ADFS hard-disc sidecar)
- [ ] `afs-init` / `afs-plan` / `afs-users` / `afs-useradd` /
  `afs-userdel` / `afs-passwd` / `afs-merge`

## Cleanup (end of Phase C)

- [x] metadata write-back on the DFS/ADFS/AFS mounts (`set_acorn_meta`).
- [x] removed `detect_filing_system`, `_navigate`, `_iter_targets`,
  `_expand_path_spec`, `open_image`, `_open_dfs`/`_open_adfs`,
  `_detect_dfs_format`, `parse_prefix`'s use, and the `FilingSystem` enum
  from `cli.py` — **no command branches on filesystem type any more.**
- [x] retired the legacy `oaknut.prober` axis + `oaknut-identify` package
  and every package's `[oaknut.prober]` entry points. `disc identify` /
  `list-formats` / `describe-format` now draw on the `oaknut.filesystem`
  coordinator, which already backed every other path.
- [x] `cli_paths.py` shrank to the fused `IMAGE_SPEC:PATH_SPEC` colon
  parser; `FilingSystem`/`resolve_path`/`parse_prefix` and the rest of the
  routing block are gone (partition selection lives in `mount.py`).

## Status

**Every generic command is migrated** onto the content-first mount +
capability substrate: ls, tree, cat, type, find, get, export,
get-load/exec, put, import, set-load/exec, chmod, lock/unlock, rm, mv,
mkdir, title, opt, cp, compact, validate, freemap, stat. The CLI no
longer branches on filesystem type for any of them.

Capabilities grown this phase: `Mount` (+ join/remove/rename), writable
`ImageReader`, `set_acorn_meta`, richer `make_directory`, `Titled.
set_title`, `DirectoryTitled`, `Bootable.set_boot_option`, `Sized`,
`PhysicalGeometry`/`DiscGeometry`, `FreeMap`/`FreeMapData`, `Compactable`,
`Validatable`, plus `.dsc` geometry resolution.

Remaining (the format-specific admin / creation axis — Phase E):

- [ ] `create`  (rework around `--filesystem` + `--geometry`)
- [ ] `generate-dsc`  (ADFS hard-disc sidecar)
- [ ] `expand`  (DFS truncated-image padding)
- [ ] `afs-init` / `afs-plan` / `afs-users` / `afs-useradd` /
  `afs-userdel` / `afs-passwd` / `afs-merge`

These create images or administer one filesystem's private structures;
they do not open-and-operate an existing partition, so they belong on a
"filesystem-contributed command" axis rather than the Mount substrate.
They are the only remaining direct importers of `oaknut.dfs/adfs/afs` in
`oaknut-disc`.

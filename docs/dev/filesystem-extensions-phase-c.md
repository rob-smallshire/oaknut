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

### Needs a structural-summary capability decision (deferred)

`stat` (disc summary), `freemap` and `validate` lean on the *physical*
CHS geometry (cylinders/heads/spt) and per-partition cylinder ranges,
free-space-map structure, and file counts. The generic `Geometry`
deliberately linearises CHS into one winchester surface and exposes only
`image_size`/`num_sectors`, so this detail is not reconstructable from
the current contract. These need a deliberate capability addition (a
`DiscSummary`/`Sized` surface and/or CHS-on-`Geometry`) before they can
migrate faithfully — grouped here rather than half-migrated.

- [ ] `stat` (disc-summary half; file-metadata half is contract-clean)
- [ ] `freemap`
- [ ] `validate`

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

### Remaining write-command work — un-stub `set_acorn_meta` first

`Mount.write_bytes(path, data)` carries no load/exec, so writing an Acorn
file with addresses = `write_bytes` + `set_acorn_meta`. `set_acorn_meta`
is the keystone and is still stubbed (`NotImplementedError`) on all three
mounts — un-stub it (DFS lock-bit only; ADFS/AFS full) and put/import/
chmod/lock/set-load/set-exec all open up. `rm`/`mv` additionally need
`remove`/`rename` (new core or capability methods); `mkdir`'s `-p`/
`--title` need a richer `make_directory`; `title`/`opt` need setters on
the Titled/Bootable capabilities.

- [ ] `set_acorn_meta` on DFS/ADFS/AFS mounts (keystone)
- [ ] `put`  (`write_bytes` + `set_acorn_meta`)
- [ ] `import`
- [ ] `cp`
- [ ] `mv`
- [ ] `rm`
- [ ] `mkdir`  (gate on HierarchicalDirectories)
- [ ] `chmod`  (gate on AcornMetadata)
- [ ] `lock` / `unlock`
- [ ] `title`  (gate on DiscMetadata)
- [ ] `opt`    (gate on DiscMetadata)
- [ ] `set-load` / `set-exec`  (gate on AcornMetadata; needs metadata write-back)
- [ ] `compact`
- [ ] `expand`

## Creation / format-specific admin (likely deferred to Phase E)

These don't fit the generic Mount model — creation needs (filesystem,
geometry); the AFS-* commands are filesystem-specific administration.
Candidates for a future "filesystem-contributed command" axis.

- [ ] `create`  (rework around `--filesystem` + `--geometry`)
- [ ] `generate-dsc`  (ADFS hard-disc sidecar)
- [ ] `afs-init` / `afs-plan` / `afs-users` / `afs-useradd` /
  `afs-userdel` / `afs-passwd` / `afs-merge`

## Cleanup (end of Phase C)

- [ ] remove `FilingSystem`, `detect_filing_system`, `parse_prefix`'s
  format role, `validate_prefix_for_image`, `open_image`, `_navigate`.
- [ ] retire the legacy `oaknut.prober` axis + `oaknut-identify` package
  and every package's `[oaknut.prober]` entry points.
- [ ] metadata write-back on the DFS/ADFS/AFS mounts (un-stub `set_acorn_meta`).

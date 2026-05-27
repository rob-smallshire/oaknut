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

## Read commands (core + capability-gated)

- [ ] `ls`
- [ ] `tree`
- [ ] `stat`
- [ ] `cat`
- [ ] `type`
- [ ] `find`
- [ ] `freemap`
- [ ] `validate`
- [ ] `get`
- [ ] `export`
- [ ] `get-load` / `get-exec`  (gate on AcornMetadata)

## Write / mutate commands

- [ ] `put`
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

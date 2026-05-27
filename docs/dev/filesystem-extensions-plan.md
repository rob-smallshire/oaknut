# Filesystem extensibility — implementation plan

**Status:** DRAFT. Executes the architecture in
[`filesystem-extensions.md`](filesystem-extensions.md). This is a
**major version bump**, so there is *no* backward-compatibility burden:
the `FilingSystem` enum, the `dfs:`/`adfs:`/`afs:` format-prefix
semantics, the format-assertion errors, and `from_file` signatures may
all change. Tests that pin the old semantics are expected to be
rewritten as the semantics change — that churn is in-scope.

## Guiding qualities

1. **The extensibility invariant is the headline acceptance criterion.**
   The base package and the CLI depend on, and import, **no** filesystem
   package. With any subset of filesystem packages installed, the tool
   works for those formats and degrades gracefully for the rest. Every
   phase is checked against this.
2. **Incremental, suite-green-ish.** Each phase lands behind the previous
   one's seams; the test suite is kept passing, adjusting tests where the
   semantics deliberately change.
3. **Adapters as scaffolding, not contracts.** New `Filesystem`
   extensions initially *wrap* the existing `DFS`/`ADFS`/`AFS` classes, so
   behaviour is preserved while the spine is built; the wrapped internals
   can be refactored later without re-touching the contract.

## Target dependency graph

The decisive change: **`oaknut-disc` stops depending on the filesystem
packages.**

```
oaknut-exception
oaknut-extension     (deps: exception, stevedore)
oaknut-file
oaknut-discimage     (deps: file)          # geometry: DiscFormat / SurfaceSpec
oaknut-basic
oaknut-filesystem    (deps: extension, discimage, file, exception)   # was oaknut-identify
    Filesystem ABC · capability protocols · geometry kinds/grammar ·
    Partition · Identification tree · identify() coordinator · ImageReader(+window)
       ▲           ▲           ▲            ▲
oaknut-dfs    oaknut-adfs   oaknut-afs   oaknut-zip      # each: deps filesystem (+ basic etc.)
   (register Filesystem extensions on the `oaknut.filesystem` entry-point axis)

oaknut-disc          (deps: filesystem, asyoulikeit, click, exception)   # NO dfs/adfs/afs
```

`oaknut-afs` keeps a dependency on `oaknut-adfs` only where it genuinely
needs the host (partition *creation* / wfsinit); the read path should
operate on a region window the coordinator supplies, so investigate
decoupling it (non-blocking).

End-user install ergonomics: `oaknut-disc` pulls only the base; a
convenience extra (`oaknut-disc[all]`) or an `oaknut[all]` metapackage
pulls the filesystem packages. The bare install must run.

## Phases

### Phase A — the contract package (`oaknut-filesystem`)

Rename/repurpose `oaknut-identify` → `oaknut-filesystem` (namespace
`oaknut.identify` → `oaknut.filesystem`; entry-point axis
`oaknut.prober` → `oaknut.filesystem`). Define the contracts:

- `Filesystem(Extension)` — `kind() == "filesystem"`; `probe(reader) ->
  Identification | None` (proposes filesystem **and** geometry +
  ambiguities); `open(reader, geometry) -> Mount`; declares its
  **geometry grammar** and any logical sub-formats.
- **Capability protocols** (`runtime_checkable`): core `Mount`
  (list/stat/read-bytes/write-bytes/exists, and *parse its own path*),
  plus `HierarchicalDirectories`, `AcornMetadata`, `BootOption`,
  `UserDatabase`, `RegionHost`.
- **Geometry**: `GeometryKind` (`floppy`, `winchester`) each with a
  grammar — named presets + a parameterised CHS parser → a discimage
  `DiscFormat`. Geometry detection is *proposed by* `probe()`.
- `Partition` (region + identity), the recursive `Identification` tree
  (per-partition, `contained` children, evidence, ambiguities),
  `ImageReader` with **windowing**, and the recursive `identify()`
  coordinator.

Tests: contract-level units with fake filesystems — geometry grammar
parse/format, coordinator ranking, recursion into `RegionHost` regions,
graceful "nothing matched". No real format packages needed yet.

### Phase B — port each filesystem as an extension (adapters)

One extension per existing class, registered on `oaknut.filesystem`:

- `oaknut-dfs`: `AcornDFS`, `WatfordDFS` (probe = today's catalogue
  `matches`; `open` wraps `DFS.from_file`; flat-directory + `AcornMetadata`
  + `BootOption`; floppy geometry grammar).
- `oaknut-adfs`: `ADFS` — `HierarchicalDirectories` + `AcornMetadata` +
  `RegionHost` (exposes reserved regions for recursion); floppy + winchester
  geometry grammar.
- `oaknut-afs`: `AFS` — found by **recursion into ADFS regions** (drop the
  whole-image `AFS0` scan; probe the windowed region); `HierarchicalDirectories`
  + `AcornMetadata` + `UserDatabase`.
- `oaknut-zip`: `Zip` — probe by `PK`; minimal core (identify-first; full
  ops optional).

Each package now depends on `oaknut-filesystem`, not `oaknut-identify`.
Tests: per-extension probe/open/capability units; the cascade on real
reference images, incl. the combined `l3fs` disc (ADFS host + AFS region
via recursion).

### Phase C — rewire the CLI onto the contract, drop filesystem deps

- `oaknut-disc` deps: remove `oaknut-dfs/adfs/afs`; keep `oaknut-filesystem`.
- Addressing (`cli_paths.py` rewrite): prefix = partition selector
  `<filesystem>[.<index>]`; the in-partition remainder is handed to the
  mounted filesystem to parse. Remove `FilingSystem`, `parse_prefix`'s
  format role, `validate_prefix_for_image`, and the content-vs-extension
  `detect_filing_system` (superseded by the coordinator).
- Options: `--filesystem <key>` and `--geometry <spec>` (no `--format`).
- Commands become **capability-gated and generic**: `ls/cat/get/put/...`
  dispatch via the core + protocols; AFS-specific commands are replaced by
  capability-gated equivalents (e.g. `disc users` on `UserDatabase`).
  `disc create` takes `--filesystem` + `--geometry`.
- Rename `list-formats`/`describe-format` → `list-filesystems`/`describe-filesystem`.
- Format-specific *admin* operations that don't generalise (wfsinit-style
  partitioning) are deferred to a possible "filesystem-contributed
  command" axis (Phase E); not in C.

Tests: the bulk of CLI test churn lands here — rewrite for partition
addressing, capability gating, and the new option/command names.

### Phase D — prove the extensibility invariant

- Audit: no module-level import of a filesystem package anywhere in
  `oaknut-filesystem` or `oaknut-disc` (add a lint/import-graph check).
- Graceful degradation: an image no installed filesystem recognises
  yields a clear message ("no installed filesystem recognises this
  image; installed: …"), never a traceback.
- **Subset-install test**: drive the coordinator/CLI with the discovered
  filesystem set filtered to a subset (primary, fast), and a CI job that
  installs only a subset in a fresh venv and smoke-tests (honest, slower).
  Assert: installed formats work; absent ones are reported unhandled.
- Install extras/metapackage so a bare `oaknut-disc` runs and `[all]`
  pulls the family.

### Phase E — additive formats & capabilities (later)

Geometry resolution for the ambiguous cases; new-map ADFS; Opus DDOS
(volumes via `HierarchicalDirectories`); DRDOS/FAT once specced;
filesystem-contributed CLI commands (wfsinit) if that axis is warranted.

## Sequencing & risk

- A and B are **additive** (new package + new extensions) — low risk, the
  old CLI keeps running on its current code throughout.
- C is the **breaking** phase (addressing, command, option, dep changes)
  and concentrates the test churn; do it as one focused, well-tested
  branch segment.
- D is where the headline quality is locked in; write the subset-install
  test *first* in D so the invariant is enforced before final cleanup.
- The bare `oaknut` metapackage and per-package `pyproject` dep edits are
  done alongside C (disc deps) and Phase A (new package wiring,
  workspace/bumpversion/testpaths entries).

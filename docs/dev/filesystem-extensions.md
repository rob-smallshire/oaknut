# Filesystem & format extensibility — design

**Status:** DRAFT for discussion (not yet implemented). Supersedes the
ad-hoc prober/prefix model that grew up under `oaknut-identify` and the
disc CLI. Capturing the target before writing code.

## 1. Why this doc

Content-based identification was added incrementally (the `oaknut.prober`
extension axis), and that incremental path surfaced a structural problem
we never designed for: **the granularities of detection, selection, and
implementation don't line up**, and several distinct concepts are
conflated under one word ("prefix"/"family"/"format").

| Concern                  | Today's granularity | Symptom                                                                                                                                   |
|--------------------------|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| Detection (probers)      | per *format*        | `acorn_dfs`, `watford_dfs` are separate probers                                                                                           |
| Selection (CLI prefix)   | per *family*        | only `dfs:` exists — you cannot ask for Watford                                                                                           |
| Implementation (classes) | mixed               | one `DFS` class hides Acorn/Watford behind a catalogue registry; one `ADFS` class hides S/M/L · old-/new-map · floppy/ST506 with no model |

`list-formats` advertises `acorn_dfs` and `watford_dfs`, but the user can
only type `dfs:` — and `dfs:` silently *means* "any DFS variant". ADFS is
the opposite: one prober, one prefix, many real but unmodelled variants
(and only old-map is detected). The model is too fine for DFS and too
coarse for ADFS.

Two further forces make this urgent:

- **More "special" formats are coming.** Acorn's DRDOS for the 80186
  Master 512 is an ADFS disc with a **FAT** filesystem in the tail
  cylinders — structurally identical to a Level 3 File Server disc,
  which is ADFS with **AFS0** in the tail. The "ADFS host + foreign
  tail" shape is a *recurring motif*, not an AFS special case, and the
  tail can be a genuinely foreign filesystem (FAT has none of Acorn's
  load/exec/access semantics).
- **Byte-exact round-tripping** (the Beebium cross-check) needs the
  *full* on-disc variant pinned down — geometry, interleave, map type,
  media — which the probers deliberately punt on today (`disc_format=None`).

## 2. The two recurring shapes

1. **A family of sibling filesystems.** Acorn DFS, Watford DDFS, Opus
   DDOS: distinct on-disc layouts sharing a heritage, mutually exclusive
   on a given disc, loosely "DFS".
2. **A host filesystem with a foreign reserved tail.** ADFS reserves
   tail cylinders in its free-space map; a second, independent
   filesystem lives there: AFS0 (L3FS) or FAT (DRDOS), with more to come.

A design that handles only one of these will keep fighting the other.

## 3. The concept stack

Separate four concepts that we have been merging:

```
Physical image
  └─ Partition scheme        how the image divides into regions
       └─ Partition(s)       a byte region of the image (host, tail, …)
            └─ Geometry       bytes → logical sectors: 40/80T · 1/2 sides · interleave · density
                 └─ Filesystem  logical sectors → files & dirs, on that geometry
```

- **Partition scheme** — most discs are whole-disc (one partition). The
  Acorn motif is "ADFS host + reserved tail region(s)". Scheme discovery
  is a capability of the host filesystem (ADFS knows it reserves a tail);
  it need not be a separate extension axis yet.
- **Partition** — a `(offset, length)` window into the image, with a
  stable identity. Identification is **per-partition**, so the answer to
  "what is this image?" is a *tree*, not a single value.
- **Geometry** — the *physical* mapping from image bytes to logical
  sectors: track count, sides, interleave, density, sector size. This is
  exactly `oaknut.discimage`'s `DiscFormat`/`SurfaceSpec`, and it sits
  *beneath* the filesystem, which reads logical sectors and is blind to
  it. The byte-identical ambiguities (80T-single vs 40T-double,
  interleaved vs sequential) are *geometry* ambiguities. **ADFS-S/M/L are
  geometry** (same structures, different size) — not filesystem variants.
  Floppy geometries enumerate as a handful of named presets; hard-disc
  geometries span an open-ended cylinders/heads/SPT space — so geometry
  selection is a *grammar*, not a fixed list (§10).
- **Filesystem** — the *logical* structure: how sectors become files and
  directories (catalogue/directory/map formats). Acorn DFS, Watford DFS,
  Opus DDOS, ADFS, AFS, FAT are *peers*. Purely-logical sub-formats (ADFS
  old-map vs new-map) are the filesystem's *own internal* concern — one
  extension may handle several, or they may be separate extensions where
  little code is shared; an encapsulation choice, **not a modelled axis**.

We deliberately drop "variant" as a single catch-all: it was conflating
*geometry* (orthogonal, physical, already modelled) with a filesystem's
*internal logical detail*. Both layers are **required inputs**, not just
detection outputs — which is why **"create an ADFS image" is
underspecified**: you must choose a geometry (S/M/L, or a hard-disc
capacity/CHS) *and* a logical format (old-map vs new-map). Today's
`ADFS.create_file` forces the geometry (you pass `ADFS_S/M/L`) and
assumes old-map. Creation is the **symmetric twin of identification**:
identify *detects* the `(geometry, filesystem)` pair, create *specifies*
it; both directions need both layers.

## 4. Filesystem as an extension

There is **one** extension type — the filesystem — with detection and
operations unified, not split across a separate prober axis. Promote the
filesystem to the extension unit on a single axis (`oaknut.filesystem`,
replacing today's `oaknut.prober`), built on `oaknut.extension`. The
current `Prober` collapses into the filesystem's `probe()` method, and
the `identify()` cascade becomes a coordinator that calls `probe()`
across the registered filesystems.

A `Filesystem` extension owns:

- **identity** — a stable hyphenated key (`acorn-dfs`, `watford-dfs`,
  `adfs`, `afs`, `fat`, …) and a human description (its docstring, as
  today). This key is the **single shared vocabulary**: `disc
  list-filesystems` enumerates the keys, `disc describe-filesystem
  <key>` explains one, and `--filesystem <key>` forces one. One name,
  three uses — no parallel lists to keep in sync.
- **probe(reader) → Identification?** — does this region look like me,
  with what confidence, evidence, and (when determinable) which variant.
- **open(reader, variant?) → mount** — return a mounted handle.
- **geometry grammar & sub-formats** — the geometry *kinds* it accepts
  (a grammar of named presets plus a parameterised CHS form, since hard
  discs are open-ended — see §10), plus any internal logical sub-formats;
  declared for detection, for `--geometry` selection, and for `disc
  create` (which needs a geometry as a required input).
- **capabilities** — a **small core** every filesystem provides (list,
  stat, read-bytes, write-bytes, exists) plus **opt-in capability
  protocols** the CLI feature-detects (`runtime_checkable`):
  `HierarchicalDirectories`, `AcornMetadata` (load/exec/access),
  `BootOption`/title, `UserDatabase` (AFS passwords/quota), `RegionHost`
  (reserves partition regions). A command like `disc afs-users` becomes
  "available when the mount provides `UserDatabase`", not "when fs is
  AFS". Foreign filesystems (FAT) simply don't advertise the Acorn
  protocols. (Decided — see §10.)
- **path interpretation** — the filesystem **owns its own in-partition
  path grammar and depth**; the CLI parses none of it (§6).

The contract must be Acorn-agnostic so FAT fits without contortion.

## 5. Partitions & recursive identification

Identification becomes recursive and per-partition:

1. Probe the whole image with every registered filesystem.
2. A winner that reserves regions (ADFS reserves cylinders in its
   free-space map) exposes those regions — **zero, one, or many** — as
   windowed sub-readers. Never assume exactly one "tail": model it as a
   collection of reserved regions. (Whether an ADFS host with several
   foreign partitions ever shipped is beside the point — the cost of
   modelling "many" is nil, and the cost of assuming "two" is a rewrite.)
3. Recurse into each reserved region, probing it with every filesystem.
   AFS, FAT, … are found there by their own detection — **ADFS stays
   ignorant of what occupies its regions** (no `oaknut-adfs →
   oaknut-afs/oaknut-fat` dependency; the recursion lives in the
   coordinator).
4. The result is the `Identification` tree, whose `contained` children
   are already a collection — realising the field we defined and left
   unused.

This requires `ImageReader` to support **windowing** (a sub-region view),
a small, clean addition. It also lets the AFS prober stop scanning the
whole image for `AFS0` and instead probe each reserved-region window.

## 6. Addressing: partitions in the path, format in options

Per the design decision: **a path prefix selects a partition and nothing
else.** A disc image is a hierarchical namespace whose top level is its
partitions; the prefix is simply the first component of the path.

```
IMAGE:PARTITION:IN-PARTITION-PATH
hd.dat:adfs:$.Apps        first ADFS partition
hd.dat:afs:$.Library      first AFS partition  (≡ afs.0:)
hd.dat:afs.1:$.Stuff      the second AFS partition, if present
floppy.ssd:$.MENU         single-partition disc — partition omitted
hd.dat:                   list the image's partitions
```

- **No format assertion in the path.** `afs:` means "the partition known
  as afs", not "interpret this disc as AFS". Naming a partition that
  isn't there is a "no such partition" error — not a format clash. The
  old "image is ADFS format; cannot access as DFS" errors disappear.
- **Format is automatic**, resolved per partition by detection.
- **Forcing is a command option, outside the path.** `--filesystem
  <key>` names a filesystem from the shared vocabulary (`--filesystem
  watford-dfs`); `--geometry <preset>` selects the physical layout. They
  are separate options because they are separate layers — there is
  deliberately **no `--format`** conflating them. Both also apply to
  `disc create`, where the geometry is a required input (you cannot
  "create ADFS" without one).

**Partition naming (decided).** A partition is selected by the
*filesystem type it was detected as*, optionally suffixed with an index:
`adfs:` / `afs:` select the **first** partition of that type — what
people mean by "the ADFS partition" or "the AFS partition", without
needing to know the low-level layout — and `afs.0:`, `afs.1:`, … select
the Nth (zero-based) when a disc holds several of one type. The name
resolves to a *partition* among those detection found; it does not assert
or force a filesystem (that is `--filesystem`). This keeps the familiar
`adfs:`/`afs:` working and survives the zero/one/many case.

**One namespace; the filesystem owns its levels.** Partitions are only
the *top* of the path — the levels at which the filesystem identity is
established. Below a partition the mounted filesystem owns the grammar
*and the depth*, and the CLI parses none of it. So depth varies by
filesystem: flat `$.NAME` (DFS), a directory tree `$.dir.name`
(ADFS/AFS), `\dir\name` (FAT) — and Opus DDOS adds up to **eight volumes
(A–H) above its directories**, `D.F.JAZZ` meaning volume D, directory F,
file JAZZ. A DDOS volume is just a deeper hierarchy level *within* one
filesystem (homogeneous), not a partition (where the filesystem can
change) — so it needs no new concept, only `HierarchicalDirectories`
plus filesystem-owned paths. (Opus DDOS manual:
`docs/dev/manuals/Opus_DDOS.pdf`; not implemented yet, noted for
generality.)

## 7. CLI dispatch

Commands resolve `(partition, filesystem, geometry)` — partition from
the path, filesystem and geometry from detection or `--filesystem` /
`--geometry` — then dispatch against the common `Filesystem` capability
interface. The existing
`if fs is DFS / elif ADFS / elif AFS` branches throughout the CLI migrate
onto that interface incrementally; AFS-only commands become "commands
gated on the AFS capability set".

## 8. Identification result model

`identify()` returns a per-partition tree. Each node carries: the
partition (region + identity), the matched filesystem, the resolved
**geometry** (a `DiscFormat`) when determinable, a confidence,
human-readable evidence, the unresolved **ambiguities** (e.g. interleaved
vs sequential — geometry the bytes can't settle), and `contained`
children. This is the single structure the CLI, `disc identify`, and the
round-trip tooling all consume.

## 9. Migration / sequencing

The concrete execution plan — target dependency graph, per-phase
deliverables, signatures, and test strategy — lives in
[`filesystem-extensions-plan.md`](filesystem-extensions-plan.md). In
outline, incremental and behind a stable interface — no big bang:

- **A. Contracts.** Define `Filesystem`, `Partition`, and the
  per-partition `Identification` tree; `Geometry` largely exists already
  as `DiscFormat`. Wrap existing `DFS`/`ADFS`/`AFS` as `Filesystem`
  extensions via adapters; keep the CLI working unchanged.
- **B. Recursive partitions.** Add `ImageReader` windowing; ADFS exposes
  its tail region; fold the AFS prober into a tail-probe; populate
  `contained`.
- **C. Addressing.** Prefix = partition only; add `--filesystem` /
  `--geometry`; rename the phase-2 `list-formats`/`describe-format`
  commands to `list-filesystems`/`describe-filesystem`; retire the
  format-assertion semantics and their errors.
- **D. CLI on the interface.** Migrate command logic off the
  per-filing-system branches onto the capability interface.
- **E. New formats.** Opus DDOS, DRDOS/FAT, new-map ADFS, full geometry
  resolution — all additive extensions.

## 10. Decisions

All review questions are now resolved; implementation follows the §9
sequence.

**Core model:**

- **One extension type.** Detection and operations are unified on a
  single `oaknut.filesystem` axis (§4); no separate prober axis. The
  prober becomes `probe()`.
- **Partition naming.** `<format>[.<index>]` — `afs:` is the first AFS
  partition, `afs.1:` the second; the selector picks a *partition*, never
  forces a format (§6). The familiar `adfs:`/`afs:` spellings survive —
  but as partition selectors with new semantics, not an API-compat promise.
- **Major version bump; no backward compatibility.** The old format-prefix
  semantics, the `FilingSystem` enum, the format-assertion errors, and the
  per-filesystem `from_file` signatures may all change freely.
- **Extensibility invariant (headline quality).** An installation works
  correctly for exactly the filesystems installed. The base package
  (`oaknut-filesystem`) and the CLI (`oaknut-disc`) depend on **no**
  filesystem package and import none at module load — filesystems are
  discovered only via entry points. Removing `oaknut-adfs` leaves
  everything working except handling ADFS (and AFS, which needs the ADFS
  host); an unhandled image degrades to a clear message, never a crash.
  A subset-install test guards this.
- **FAT is not in scope yet** — too little known about its on-disc
  detail. It stays the motivating example for host-plus-foreign-tail
  recursion and the Acorn-agnostic contract, so the design must *admit*
  it later without rework; we build nothing FAT now.
- **Capability interface = small core + opt-in protocols** (§4), not one
  fat ABC. The filesystem also owns its in-partition path grammar/depth,
  so Opus DDOS volumes are just a deeper hierarchy level, not a new
  concept.
- **Two orthogonal layers, no "variant".** *Geometry* (physical: tracks,
  sides, interleave, density — the discimage `DiscFormat`) sits beneath
  the *filesystem* (logical structure). The vague "variant" is dropped:
  it splits into geometry (modelled, orthogonal) and a filesystem's own
  internal logical detail (§3). A mount is `(geometry, filesystem)`.
- **Terminology: `filesystem` and `geometry`, never `format`.** The two
  layers are the only nouns. `--filesystem <key>` forces the filesystem,
  `--geometry <preset>` the layout — there is **no `--format` option**
  (an option named "format" that set a filesystem was exactly the
  vagueness we are removing). "format" may appear in prose only as
  shorthand for the complete `(filesystem, geometry)` tuple. The phase-2
  `list-formats`/`describe-format` commands become
  `list-filesystems`/`describe-filesystem`.
- **No separate coordinator package.** `oaknut.identify` folds into
  `oaknut.filesystem`: the base package houses the `Filesystem` contract,
  capability protocols, `Partition`, the `Identification` tree, **and**
  the `identify()` coordinator. Format packages depend on it and register
  filesystems on the `oaknut.filesystem` axis. (`oaknut-identify` becomes
  `oaknut-filesystem`; namespace `oaknut.prober` → `oaknut.filesystem`.)

**Geometry & naming:**

1. **Geometry → a filesystem-declared *grammar*, not a flat preset
   list.** A fixed preset enum works for floppies (ADFS `s`/`m`/`l`;
   DFS's small tracks×sides×density×interleave space) but **not** for
   hard discs, whose cylinders/heads/SPT/sector-size space is
   open-ended and can't be pre-enumerated. So `--geometry <spec>` is
   interpreted by the chosen filesystem's grammar, admitting both **named
   presets** (the enumerable, common cases — shown by
   `describe-filesystem`, used by `disc create`) and a **parameterised
   form** (e.g. `cylinders=…,heads=…,spt=…`). The grammars are likely
   shared **geometry kinds** — `floppy` (tracks/sides/density/interleave)
   and `winchester` (cylinders/heads/spt/sector-size) — that a filesystem
   declares it accepts, rather than each reinventing one. `probe()`
   proposes a geometry in the same grammar (#2); the resolved target is a
   discimage `DiscFormat`.
2. **`probe()` proposes the geometry.** The filesystem is the only thing
   that can read its own capacity hints (DFS catalogue sector count, ADFS
   disc record), so `probe()` returns the filesystem identity *plus* a
   candidate geometry and any byte-identical ambiguities — not a separate
   blind geometry step. The discimage layer supplies the geometry *kinds*;
   the filesystem says which point fits.
3. **"Family" (DFS) is not a code concept.** `acorn-dfs` and `watford-dfs`
   are independent filesystems — historically related, implementation may
   share code, but independent at the user level. "DFS" is at most a
   documentation grouping. No family enum; today's `FilingSystem` enum is
   replaced by the filesystem-key vocabulary plus partition selectors.

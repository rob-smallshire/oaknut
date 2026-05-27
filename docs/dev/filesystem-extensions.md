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

| Concern | Today's granularity | Symptom |
|---|---|---|
| Detection (probers) | per *format* | `acorn_dfs`, `watford_dfs` are separate probers |
| Selection (CLI prefix) | per *family* | only `dfs:` exists — you cannot ask for Watford |
| Implementation (classes) | mixed | one `DFS` class hides Acorn/Watford behind a catalogue registry; one `ADFS` class hides S/M/L · old-/new-map · floppy/ST506 with no model |

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
            └─ Filesystem     the read/write implementation occupying it
                 └─ Variant   that filesystem's concrete on-disc parameters
```

- **Partition scheme** — most discs are whole-disc (one partition). The
  Acorn motif is "ADFS host + reserved tail region(s)". Scheme discovery
  is a capability of the host filesystem (ADFS knows it reserves a tail);
  it need not be a separate extension axis yet.
- **Partition** — a `(offset, length)` window into the image, with a
  stable identity. Identification is **per-partition**, so the answer to
  "what is this image?" is a *tree*, not a single value.
- **Filesystem** — the pluggable unit (see §4). Acorn DFS, Watford DFS,
  Opus DDOS, ADFS, AFS, FAT are *peers*. (DFS is a family of sibling
  filesystems; ADFS is one filesystem with many variants — the model
  must accommodate both.)
- **Variant** — the concrete parameters needed to read *and write*
  byte-exactly. Richer than today's `DiscFormat` (geometry + catalogue
  name): also map type, media, interleave, the unresolvable ambiguities.

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
  list-formats` enumerates the keys, `disc describe-format <key>`
  explains one, and `--format <key>` forces one. One name, three uses —
  no parallel lists to keep in sync.
- **probe(reader) → Identification?** — does this region look like me,
  with what confidence, evidence, and (when determinable) which variant.
- **open(reader, variant?) → mount** — return a mounted handle.
- **variants** — the set it supports, for detection and for `--format`.
- **capabilities** — the operations it supports, against a *common*
  interface (list, stat, read-bytes, write-bytes, mkdir, …) so the CLI
  can dispatch generically. Acorn-specific metadata (load/exec, access
  bits, boot option) is an *optional* capability a foreign filesystem
  like FAT simply doesn't advertise.

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
- **Forcing format is a command option, outside the path** — `--format
  <key>`, where `<key>` is a filesystem from the shared vocabulary
  (`--format watford-dfs`, `--format acorn-dfs`). It overrides
  misdetection without polluting the path grammar. *(Open: forcing a
  finer **variant** — the byte-identical DFS single-vs-double/interleave
  ambiguity, or ADFS S/M/L — may need a separate knob or a compound
  value like `acorn-dfs:80t-double`; see §10.)*

**Partition naming (decided).** A partition is selected by the
*filesystem type it was detected as*, optionally suffixed with an index:
`adfs:` / `afs:` select the **first** partition of that type — what
people mean by "the ADFS partition" or "the AFS partition", without
needing to know the low-level layout — and `afs.0:`, `afs.1:`, … select
the Nth (zero-based) when a disc holds several of one type. The name
resolves to a *partition* among those detection found; it does not assert
or force a format (that is `--format`). This keeps the familiar
`adfs:`/`afs:` working and survives the zero/one/many case.

## 7. CLI dispatch

Commands resolve `(partition, filesystem, variant)` — partition from the
path, filesystem+variant from detection or `--format` — then dispatch
against the common `Filesystem` capability interface. The existing
`if fs is DFS / elif ADFS / elif AFS` branches throughout the CLI migrate
onto that interface incrementally; AFS-only commands become "commands
gated on the AFS capability set".

## 8. Identification result model

`identify()` returns a per-partition tree. Each node carries: the
partition (region + identity), the matched filesystem, the **variant**
when determinable, a confidence, human-readable evidence, the unresolved
**ambiguities** (e.g. interleaved vs sequential), and `contained`
children. This is the single structure the CLI, `disc identify`, and the
round-trip tooling all consume.

## 9. Migration / sequencing

Incremental, behind a stable interface — no big bang:

- **A. Contracts.** Define `Filesystem`, `Variant`, `Partition`, and the
  per-partition `Identification` tree. Wrap existing `DFS`/`ADFS`/`AFS`
  as `Filesystem` extensions via adapters; keep the CLI working unchanged.
- **B. Recursive partitions.** Add `ImageReader` windowing; ADFS exposes
  its tail region; fold the AFS prober into a tail-probe; populate
  `contained`.
- **C. Addressing.** Prefix = partition only; add `--format`; retire the
  format-assertion semantics and their errors.
- **D. CLI on the interface.** Migrate command logic off the
  per-filing-system branches onto the capability interface.
- **E. New formats.** Opus DDOS, DRDOS/FAT, new-map ADFS, full
  variant/geometry resolution — all additive extensions.

## 10. Decisions & open questions

**Resolved in review:**

- **One extension type.** Detection and operations are unified on a
  single `oaknut.filesystem` axis (§4); no separate prober axis. The
  prober becomes `probe()`.
- **Partition naming.** `<format>[.<index>]` — `afs:` is the first AFS
  partition, `afs.1:` the second; the selector picks a *partition*, never
  forces a format (§6). `adfs:`/`afs:` therefore stay working
  (backward compatible).
- **FAT is not in scope yet** — too little known about its on-disc
  detail. It stays the motivating example for host-plus-foreign-tail
  recursion and the Acorn-agnostic contract, so the design must *admit*
  it later without rework; we build nothing FAT now.

**Still open:**

1. **Capability interface shape** — one fat `Filesystem` ABC, or a small
   core plus opt-in capability mixins (Acorn metadata, hierarchical dirs,
   region-host)? FAT and DFS having very different surfaces argues for
   mixins.
2. **`--format` granularity** — force just the filesystem, or also the
   **variant** (DFS single-vs-double/interleave, ADFS S/M/L)? Per selected
   partition or whole-image?
3. **Where variant detection lives** — `probe()` returns a variant, vs a
   separate variant-resolution step once the filesystem is known.
4. **Is "family" (DFS) a code concept** at all, or just a loose grouping
   of `--format` values? Leaning: not first-class.
5. **Coordinator home** — does `identify()` (the cascade + result tree)
   stay in `oaknut.identify`, or move into the unified `oaknut.filesystem`?

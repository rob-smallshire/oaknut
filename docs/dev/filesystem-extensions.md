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

Promote the filesystem itself to the extension unit, on a new axis
(`oaknut.filesystem`), built on the existing `oaknut.extension`
framework. The current `Prober` becomes the **detection facet** of a
filesystem, not a separate axis.

A `Filesystem` extension owns:

- **identity** — a stable name (`acorn-dfs`, `watford-dfs`, `adfs`,
  `afs`, `fat`, …) and a human description (its docstring, as today).
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
2. The winner that *reserves a tail* (ADFS) exposes its tail region as a
   windowed sub-reader.
3. Recurse: probe the tail region with every filesystem. AFS, FAT, … are
   found there by their own detection — **ADFS stays ignorant of what
   occupies its tail** (no `oaknut-adfs → oaknut-afs/oaknut-fat`
   dependency; the recursion lives in the coordinator).
4. The result is the `Identification` tree, realising the `contained`
   field we defined and left unused.

This requires `ImageReader` to support **windowing** (a sub-region view),
which is a small, clean addition. It also lets the AFS prober stop
scanning the whole image for `AFS0` and instead probe the tail window.

## 6. Addressing: partitions in the path, format in options

Per the design decision: **a path prefix selects a partition and nothing
else.** A disc image is a hierarchical namespace whose top level is its
partitions; the prefix is simply the first component of the path.

```
IMAGE:PARTITION:IN-PARTITION-PATH
hd.dat:adfs:$.Apps        the ADFS host partition
hd.dat:afs:$.Library      the AFS tail partition
hd.dat:fat:\AUTOEXEC.BAT  a FAT tail (DRDOS), with native separators
floppy.ssd:$.MENU         single-partition disc — partition omitted
hd.dat:                   list the image's partitions
```

- **No format assertion in the path.** `afs:` means "the partition known
  as afs", not "interpret this disc as AFS". Naming a partition that
  isn't there is a "no such partition" error — not a format clash. The
  old "image is ADFS format; cannot access as DFS" errors disappear.
- **Format is automatic**, resolved per partition by detection.
- **Forcing format is a command option, outside the path** — e.g.
  `--format watford-dfs`, `--format adfs-l`. This is where the
  byte-identical ambiguities (DFS single-vs-double, interleave) and any
  misdetection are resolved, without polluting the path grammar.

**Open:** how are partitions *named*? Naming the tail after its detected
filesystem (`afs`, `fat`) is the most intuitive and is what users say,
but it re-introduces a format flavour into a partition name. Alternatives:
role-based (`host`/`tail`), or ordinal (`0`/`1`). See §10.

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

## 10. Open questions

1. **Partition naming** — by detected filesystem (`afs`, `fat`), by role
   (`host`, `tail`), or ordinal? Trade intuition against the "partition ≠
   format" principle.
2. **Is "family" (DFS) a code concept** at all, or just a grouping of
   `--format` values / a detection convenience? Leaning: not a first-class
   runtime concept.
3. **Backward compatibility** — `adfs:`/`afs:` already ship as prefixes.
   Keep them working as partition names during/after migration?
4. **`--format` scope** — does it force a named partition's filesystem,
   its variant, or both? Per-partition or whole-image?
5. **Capability interface shape** — one fat `Filesystem` ABC, or a small
   core plus opt-in capability mixins (Acorn metadata, hierarchical dirs,
   tail-host)?
6. **Where variant detection lives** — `Filesystem.probe` returns a
   variant, vs a separate variant-resolution step.
7. **Package/axis naming** — `oaknut.filesystem`? Does `oaknut.identify`
   fold into it, or stay as the detection coordinator over it?
8. **Foreign filesystems** — is FAT in-scope for oaknut to read/write, or
   only to *identify* (so `disc identify` names it but operations defer)?

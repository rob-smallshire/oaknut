# Proposal: Acorn Level 3 File Server filesystem support (`oaknut-afs`)

Status: discussion draft
Author: initial sketch, for further refinement

## 1. What is this filesystem and what should we call it?

WFSINIT is the Acorn-supplied BBC BASIC utility that prepares a SCSI hard disc
for use with the **Acorn Level 3 File Server** (L3FS). A few names get used
more-or-less interchangeably for the filesystem it creates, and it's worth
separating them before picking one:

| Name  | Origin                                                                                 |
|-------|----------------------------------------------------------------------------------------|
| AFS   | The magic bytes at the start of each info sector are literally `"AFS0"`               |
| WFS   | "Winchester File System/Server" — derived from the utility's name `WFSINIT`           |
| L3FS  | The file server product as a whole ("Level 3 File Server")                            |

Two names should **not** be in that list:

- **NFS / ANFS** live at a different layer. They are the *client-side*
  network filing systems (the Econet protocol the BBC Micro or Master uses
  to talk to an L3FS). Our filesystem is the server's private, on-disc
  representation — the two layers just happen to share a disc trip. Calling
  our module "NFS" would be wrong. (Beebmaster's document uses "NFS
  partition" as a shorthand, but conflates the layers.)
- **L3FS** is the product, not the format. The on-disc layout is only one of
  several things the Level 3 File Server is; reusing the product name for
  the format would obscure that distinction.

The cleanest evidence for the name is the `AFS0` magic in the info sector
(pdf p.6, `wfsinit.md` §6) — that is how the code on disc identifies itself.
So: the package is **`oaknut-afs`** and the module is **`oaknut.afs`**.
WFSINIT is then "the partitioner for AFS", which reads naturally.

What the `A` actually stands for is genuinely unclear. "Acorn File Server"
is the obvious guess — it matches the `0` as a format version and gives a
clean expansion — but I have seen no primary source that spells it out.
Worth noting in the module docstring as "origin uncertain; likely *Acorn
File Server*" rather than asserting it as fact.

## Primary sources

Three pieces of material together constitute the working specification for
this project. They are listed in decreasing order of authority:

1. **Level 3 File Server ROM source, version 1.26.**
   `/Users/rjs/Code/L3V126/` — ~27k lines of 6502 assembly, originally
   uploaded to Stardot by Alan Williams and reformatted for BeebAsm by
   Martin Mather. This is the actual file server that wrote and read these
   discs in the field; when the three sources disagree, the ROM wins. The
   module layout maps cleanly onto the concerns we need to implement:

   | Module            | File(s)         | What it tells us                            |
   |-------------------|-----------------|---------------------------------------------|
   | Header / workspace| `Uade01`–`Uade02` | Authoritative on-disc struct layouts      |
   | USRMAN            | `Uade06`        | User management                             |
   | STRMAN            | `Uade0A`–`Uade0B` | Open file / stream management              |
   | DIRMAN            | `Uade0C`–`Uade0E` | **Directory growth past 19 entries**       |
   | AUTMAN            | `Uade0F`        | Authorisation + quota credit/debit rules    |
   | MAPMAN            | `Uade10`–`Uade13` | **Map-sector chaining for large files**    |
   | MBBMCM            | `MBBMCM.asm`    | Bit-map / map-block **cache manager** (allocation *policy* is in MAPMAN) |
   | DSCMAN            | `Uade14`        | Disc-level operations                        |
   | RNDMAN            | `Rman01`–`Rman05` | Random access: **extend / truncate**       |

2. **"Understanding the Acorn Level 3 File Server Structure"** by ISW (2010),
   at `/Users/rjs/Code/beebium/scripts/wfsinit/Understanding the Acorn Level 3 File Server Structure.pdf`.
   A reverse-engineered tour of a WFSINIT-created test disc with worked hex
   examples. Excellent for cross-checking the ROM: if you can't see what a
   routine in MAPMAN is doing, the PDF probably has a dump showing its
   output on disc.

3. **WFSINIT BBC BASIC source + write-up.**
   `/Users/rjs/Code/beebium/scripts/wfsinit/WFSINIT.bas` and
   `wfsinit.md`. The disc *initialiser*, not the running server — so it
   only describes the freshly-minted state. Authoritative for the
   partitioning step (shrinking ADFS, installing `&F6`/`&1F6` pointers,
   writing the initial info sectors, bitmaps, root directory and passwords
   file), but silent on everything that happens after a disc is in service.

**Working approach for the ROM source:** read `Uade01`/`Uade02` cover-to-
cover up front (the struct-layout headers), then treat the rest as a
reference manual — open a module only when you have a specific question.
Capture findings into `docs/afs-onwire.md` as you extract them, citing the
exact assembly file and label, so the next person (including future-you)
does not have to re-read the ROM to reconstruct the answers.

## 2. How does AFS relate to ADFS on the same disc?

An AFS-prepared disc is, structurally, an **ADFS disc with a shrunken free
space map that sets aside a tail region for AFS**. Two representations of the
same bytes coexist:

1. **ADFS** sees a disc whose nominal size field (`OLD_SIZE_OFFSET`, sector 0
   byte `&FC`) has been reduced so that cylinders from `stcyl%` onwards are
   "off the end of the disc" from ADFS's point of view. Two otherwise-unused
   words in the reserved area of sector 0/1 (`&F6` and `&1F6`) point at the
   two redundant copies of the AFS info sector.
2. **AFS** sees the region from cylinder `stcyl%` to the physical end of the
   disc, with its own per-cylinder bitmap sectors, two copies of an info block
   (`"AFS0"` magic), a root directory, a passwords file, and files laid out as
   (SIN → JesMap → extent list → data) chains.

The partitioning is **not** a generic partition table. It is specific to the
ADFS old-map format (S/M/L/D-style) and relies on two reserved-word pointers
that are otherwise unused in a plain ADFS disc. There is no equivalent for the
new-map (E/E+/F/F+) ADFS format, because that format uses its reserved bytes
differently — AFS is an artefact of the old-map era. The existing
`oaknut.adfs.free_space_map.OldFreeSpaceMap` is therefore the right place to
surface AFS awareness: an old-format map object can optionally report a pair
of AFS info-sector pointers.

### Proposed object model

```
UnifiedDisc (oaknut.discimage)
    │
    ├── ADFS(disc)                       # existing, unchanged
    │     └── .afs_partition             # NEW: Optional[AFS], lazily constructed
    │                                    #     None if sector-0 bytes &F6/&1F6 are 0
    │                                    #     or if the map is new-format.
    │
    └── AFS.from_disc(disc)              # NEW: direct entry point when caller
                                         #     already knows it is an AFS disc or
                                         #     wants to bypass ADFS entirely.
```

The arrow from `ADFS` to `AFS` is one-way: opening as ADFS lets you *discover*
the AFS partition if it exists. The reverse direction is not needed — the AFS
code does not care about ADFS contents, only about the `startcyl%` value in
its own info block and the physical geometry of the disc.

`AFS` itself holds a `SectorsView` scoped to the AFS region (from cylinder
`startcyl%` to end-of-disc) and interprets it through AFS-native structures.
It does **not** re-use `oaknut.adfs.directory` — AFS directories are a
completely different format (17-byte header, 26-byte entries, two linked
lists, master-sequence-number tail byte).

### What a user sees

```python
from oaknut.adfs import ADFS

with ADFS.from_file("l3fs-master.img") as adfs:
    print(adfs.root.name)                  # ADFS side still works
    afs = adfs.afs_partition               # or None
    if afs is not None:
        print(afs.disc_name)               # "Level3MasterDisc"
        for entry in afs.root:
            print(entry.name, entry.access_str)
        hello = (afs.root / "BeebMaster" / "!Boot").read_bytes()
```

Opening directly:

```python
from oaknut.afs import AFS

with AFS.from_file("l3fs-master.img") as afs:
    ...
```

The direct form would still read the ADFS free-space map pointers at
`&F6`/`&1F6` to locate the info sectors. It just skips constructing an `ADFS`
facade for a caller who doesn't need it.

## 3. Can we replicate WFSINIT in Python?

Yes, and we should — but as a **library-first** capability with a thin CLI on
top, not as a literal port of the BASIC. WFSINIT's behaviour decomposes into
these separable operations, all of which are straightforward once we have
`SectorsView` access:

| Operation                                | Inputs                                | Oaknut module                                          |
|------------------------------------------|---------------------------------------|--------------------------------------------------------|
| Compute `stcyl%` from current ADFS usage | `OldFreeSpaceMap`                     | `oaknut.afs.partition.compute_start_cylinder`          |
| Shrink the ADFS partition                | `OldFreeSpaceMap`, `stcyl%`           | `oaknut.adfs.free_space_map.OldFreeSpaceMap.shrink_to` |
| Install AFS `&F6`/`&1F6` pointers        | `OldFreeSpaceMap`, `sec1%`, `sec2%`   | same object                                            |
| Write per-cylinder bitmap sectors        | `SectorsView`, geometry               | `oaknut.afs.bitmap`                                    |
| Write `AFS0` info block (×2)             | disc name, date, geometry, root SIN   | `oaknut.afs.info_sector`                               |
| Create the `$` root directory            |                                       | `oaknut.afs.directory`                                 |
| Create a passwords file                  | user list                             | `oaknut.afs.passwords`                                 |
| Create a per-user URD                    | user name                             | `oaknut.afs.directory`                                 |
| Populate `Library`, `Utils`, `Welcome`   | a source directory (tar, host dir, …) | `oaknut.afs.populate`                                  |

A high-level driver — `oaknut.afs.wfsinit.initialise(disc, *, disc_name,
users, populate_from=None)` — composes these into the same sequence the BASIC
program performs, minus the hardware-specific bits (no OSWORD &72, no MODE 7
UI). The driver must refuse to run unless:

- the ADFS map is old-format;
- the ADFS free-space list contains exactly one free extent at the tail
  (i.e. the disc is compacted — WFSINIT's "fully compacted" precondition);
- the disc has not already been AFS-initialised (the `&F6`/`&1F6` pointers
  are both zero).

**On populating libraries:** the econet-fs.tar corpus at
`/Users/rjs/Code/beebium/discs/l3fs/libraries/econet-fs.tar` carries
PiEconetBridge xattr metadata, and our `oaknut-file` package already knows
how to round-trip Acorn metadata via its `host_bridge`. The `populate` step
should therefore accept *any* oaknut `host_bridge` source (a directory with
sidecars, a tar, or eventually a SparkFS zip) and not be hard-coded to the
BASIC's floppy layout. This also immediately generalises to placing
modern-curated libraries, not just Acorn 1985 originals.

**Things we will deliberately *not* replicate:**

- The OSFILE-5-without-return-check phantom-entry bug described in
  `wfsinit.md` §Phase 8.
- The `&40404` (256 KB) default user quota, which is too small for any disc
  worth partitioning. Default to something sensible (e.g. `&40000000`, as the
  beebmaster test disc uses) with an explicit parameter to override. This
  matches the `feedback_spt_default_33` pattern: pick a better default, keep
  the knob.
- The `DIM inside FNopen` memory leak and the `GOTO` between `DEF PROC`s.

## 4. Can we implement read/write for AFS?

Yes. Read-only first, then write. The work factors cleanly by layer.

### Read path

1. **Geometry + info sector**: follow either the ADFS-side pointers or, given
   a known `startcyl%`, read sector `stcyl%*spc + 1`, verify `AFS0`, pull out
   `disc_name`, `nocyls%`, `nosecs%`, `secpcyl%`, root SIN, `startcyl%`, date.
2. **Per-cylinder bitmap**: lazily read sector 0 of each cylinder as needed.
   For a read path this is only required if we want to report free space.
3. **Map sector (JesMap) decoder**: takes a SIN, reads the sector, verifies
   the `JesMap` magic and sequence-number tail, decodes the extent list,
   and returns an object that behaves like a `SectorsView` concatenation over
   the extents. Object size is `(total_sectors - 1) * 256 + lsb_byte`.
4. **Directory decoder**: takes a map-sector-resolved byte stream, walks the
   in-use linked list from header bytes 0–1, yields 26-byte entries sorted
   alphabetically (already in list order). Verifies `master_seq == tail_byte`.
5. **Path resolution**: pathlib-inspired, mirroring `ADFSPath`. `$` is root;
   separator is `.`; names are up to 10 characters.
6. **Passwords file**: the root directory's `Passwords` entry (access `&00`)
   points to a chain of 31-byte user records. Expose them read-only.

### Write path

The write path is more involved because several operations have semantics
that WFSINIT and the Beebmaster write-up do not document — they only show
the state of a freshly-initialised disc. For each of these, the authoritative
reference is the L3V126 ROM source. The items below flag the specific module
to consult.

- **Allocation**: pick the cylinder with the most free space, find the first
  free bit in its bitmap, allocate a map sector there, then contiguous data
  sectors after it; spill to further cylinders for long files, recording
  each run as a 5-byte extent. Maintain a shadow "cylinder map" (total
  free, per-cylinder free) to avoid scanning every bitmap sector on each
  allocation. WFSINIT's `FNablk` is one implementation of this, but the
  running server's heuristic (in MAPMAN, `Uade10`–`Uade13` — not MBBMCM,
  which is the cache manager) is the one to match if we want discs that the
  real server will accept as well-formed.
- **Free**: walk the map sector's extents, set bits back to 1, increment the
  shadow cylinder map, rewrite bitmap sectors touched. Cross-check with
  MAPMAN's DAGRP/CLRBLK for any edge cases around partially-freed extents.
- **Map-sector chaining for large files.** Undocumented in both WFSINIT and
  the PDF. Reference: **MAPMAN** (`Uade10`–`Uade13`) — the sequence number
  at byte 6/255 exists specifically to support multiple map sectors per
  file, and MAPMAN is where chain traversal and extension live.
- **File extend / truncate.** Not in WFSINIT (which only writes fixed-size
  files from floppy). Reference: **RNDMAN** (`Rman01`–`Rman05`) +
  MAPMAN. Key question: does the server extend the last extent in place
  when contiguous free space exists, or always append a new extent?
- **Directory insert**: pop a slot off the free list, splice into the
  in-use list at the alphabetical insertion point, bump `master_seq` (and
  its tail copy), fill name/load/exec/access/date/SIN.
- **Directory growth past 19 entries.** Undocumented in both WFSINIT (which
  only ever creates the initial 2-sector directory) and the PDF (which
  asserts that growth happens but not how). Reference: **DIRMAN**
  (`Uade0C`–`Uade0E`). The question to answer: does the server allocate a
  new, larger directory object and migrate entries, or chain a second
  directory block?
- **Directory delete**: reverse splice, push slot onto the free list, bump
  `master_seq`. Never actually zero the slot's data bytes (WFSINIT doesn't).
  DIRMAN will confirm whether that is safe under the server's own reader.
- **Space accounting**: every create/delete/extend debits/credits the
  owner's quota in the passwords file. This is easy to get wrong silently,
  so unit tests should assert the invariant
  `sum(user_free) + used == capacity` on every mutation. Reference:
  **AUTMAN** (`Uade0F`) for the exact credit/debit points.
- **Checksums**: AFS itself has no per-sector checksum, but shrinking the
  ADFS side requires re-running the 255-byte end-around-carry checksum on
  both halves of ADFS sector 0. `oaknut.adfs.free_space_map` already owns
  that code; we reuse it.

### Layering

`oaknut-afs` depends on `oaknut-file`, `oaknut-discimage`, and (softly)
`oaknut-adfs` — the ADFS dependency exists because initialising a disc
requires mutating the ADFS free space map. Reading a pre-existing AFS
partition does not strictly require ADFS at all if you already know
`startcyl%`, so the dependency on ADFS could be made optional/dev-time if
we care about minimising runtime deps. My default would be to make
`oaknut-adfs` a hard dependency and accept the small extra weight — the two
filesystems come together.

AFS sits as an independent sibling to `oaknut-dfs` and `oaknut-adfs`, just as
those two already are to each other. `from oaknut.adfs import AFS` is
deliberately not a thing, for the same reason `from oaknut.dfs import ADFS`
is deliberately not a thing.

## 5. Open questions

1. **Name.** `afs` vs `l3fs` vs `wfs`. My vote: `afs`, to match the magic.
2. **New-map ADFS.** Do we need to support AFS on top of new-map ADFS at all?
   Beebmaster's document and WFSINIT both assume old-map. I'd start by
   refusing to partition a new-map disc and revisit only if a counter-example
   appears.
3. **Multi-drive file servers.** `addfact%`/`drinc%` hint at multi-drive
   configurations where AFS spans several SCSI drives. Do we want to model
   that at the Python level (a `MultiDriveAFS` that concatenates several
   `UnifiedDisc`s), or treat each drive as its own AFS and leave stitching
   to the caller? I'd punt on this for v1.
4. **Test corpus.** We have beebmaster's test disc description in the PDF,
   plus the `econet-fs.tar` library tree. We should also cut a small
   synthetic AFS image in Python as soon as `initialise()` exists, and commit
   it under `tests/data/images/` for use as a read-only regression fixture.
   (See `feedback_test_data_in_git`.) A round-trip test — initialise, add a
   few files, reopen, read them back — is worth writing before the allocator
   is fully optimised.
5. **File content on disc.** WFSINIT's copy step transfers file bytes via
   OSGBPB 4 and does not preserve xattrs. Our populate path should preserve
   xattrs via `host_bridge`, but there is nowhere in the AFS directory entry
   to *store* anything beyond load/exec/access/date/SIN. Anything richer
   (RISC OS filetype, original filename case) is lost on the way in. That's
   a limitation of the target format and not something we should paper over.

## 6. Suggested implementation order

1. **Read `Uade01`/`Uade02` from L3V126**, cover-to-cover, and start
   `docs/afs-onwire.md` — a living specification that records the
   authoritative struct layouts, workspace offsets, and any workspace
   constants we will need to interpret later modules. Cite each fact to
   `Uade0x.asm:<label>`. This is the one piece of the ROM we read
   eagerly; everything else is read on demand.
2. Scaffold `packages/oaknut-afs` following the existing workspace pattern
   (no `src/oaknut/__init__.py`!), with bumpversion config and a namespaced
   tag format.
3. Read path, in layers: info sector → single-map-sector file → directory
   (static, ≤19 entries) → path resolution → passwords file. Each layer
   gets unit tests against a hand-crafted bytes fixture, plus a regression
   test against the beebmaster test-disc hex dumps from the PDF, before
   the next layer is written.
4. `ADFS.afs_partition` attribute, exposed on the existing ADFS object.
5. Read-path completeness: consult **MAPMAN** for chained-map-sector files
   and **DIRMAN** for grown directories, implement both, and extend
   `afs-onwire.md` with the findings.
6. Write path: allocator + bitmap updates + directory mutation, guided by
   **MAPMAN** and **DIRMAN**. Quota credit/debit per **AUTMAN**. Behind a
   feature flag until round-trip tests (initialise → populate → reopen →
   verify) are solid.
7. File extend / truncate, guided by **RNDMAN** + **MAPMAN**.
8. `wfsinit.initialise()` driver, composed from the pieces above, with the
   ADFS old-map shrink routine landed in `oaknut-adfs` alongside it.
9. A small `afs` sub-command in the forthcoming `disc` CLI (see
   `docs/cli-design.md`) that wraps `initialise()`, `ls`, `cat`, `put`.

Test-first throughout, per project convention.

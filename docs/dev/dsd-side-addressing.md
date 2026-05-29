# Addressing both sides of a double-sided DFS image

**Status:** draft for iteration, 2026-05-29. Nothing here is decided — flag
anything you want to change. Amend this file in place; commit history is the
discussion log.

## Context

A user (Mark) asked how to copy onto the second side of a double-sided DFS
image he is assembling from two BeebAsm-built SSDs:

```sh
disc create elite.dsd --title "Compendium E"
disc cp "drive-0.ssd:*" elite.dsd       # works — lands on side 0
disc cp "drive-2.ssd:*" elite.dsd:???   # no syntax reaches side 2
```

There is no such syntax. This is a genuine gap, not a documentation hole:

- The DFS filesystem adapter's `open()`
  (`packages/oaknut-dfs/src/oaknut/dfs/filesystem.py`) calls
  `DFS.from_buffer(reader.buffer(), disc_format)` with **no `side`
  argument** — it always mounts surface 0.
- `probe()` returns a single `Identification` carrying the double-sided
  *geometry* but never surfaces the second side as a partition, so
  `partition_selectors(elite.dsd)` returns only `['acorn-dfs']`.
- `disc stat` on a 400 KiB DSD reports `Size 204800` — it sees one side.
- There is no `--side` flag and no selector that reaches the second side.

The `oaknut.dfs` library itself fully supports both sides:
`DFS.from_buffer(buffer, double_sided_format, side=N)` opens either,
writably, over the live file. The gap is purely in the CLI / identification
exposure.

## Domain background: sides are *drives*, and they are separate surfaces

On a real BBC Micro, Acorn DFS presents the two surfaces of a floppy as
different **drives**, not sides:

| Drive | Meaning                          |
|-------|----------------------------------|
| 0     | first physical drive, side 0     |
| 2     | first physical drive, side 1     |
| 1     | second physical drive, side 0    |
| 3     | second physical drive, side 1    |

The scheme is historical: early machines had only single-sided drives, so 0
and 1 were the two *physical* drives; the second side of each was added
later as 2 and 3. This is why Mark reached for `:2` — it is the authentic
Acorn address for "the other side of this disc."

A single `.dsd` image represents **one physical drive**, so its two sides
are always **drive 0 and drive 2** — never 1 or 3 (those belong to the
absent second drive).

Crucially, each side is a **fully independent DFS volume** — its own
catalogue, title, boot option, cycle number and free space — physically a
**separate surface**, not a sector-range region of a shared volume. This
distinction drives the whole design (see *Why a side is not a reserved
region* below).

## Goal

Present a double-sided DFS image as a disc carrying **two DFS partitions**,
reusing the existing partition-selector convention:

```sh
disc cp "drive-0.ssd:*" elite.dsd          # bare → drive 0 (default)
disc cp "drive-2.ssd:*" elite.dsd:2:       # explicit → drive 2
disc cp "drive-0.ssd:*" elite.dsd:0:       # explicit → drive 0
disc ls   elite.dsd:2:$
disc stat elite.dsd:2:
```

This inherits the no-selector-means-first-partition rule the CLI already
applies (`mount.py:_select` returns the host when the selector is `None`),
so existing `elite.dsd:…` commands keep meaning drive 0 and nothing
regresses.

## Why a side is not a reserved region (the crux)

The instinct is to reuse the machinery that already exposes an AFS tail
inside an ADFS disc: a `Partition` is a *logical-sector run*
`(start_sector, num_sectors)` recorded in `Identification.reserved_regions`,
and the coordinator recurses into it via `region_reader`. **That mechanism
is wrong for DFS sides**, for one decisive reason:

> `region_reader` (`geometry.py`), for an **interleaved host** — which every
> double-sided floppy is — de-interleaves the region into a **read-only
> copy** and *refuses writes outright*:
>
> ```
> GeometryError: writing to an interleaved reserved region (e.g. AFS on a
> double-sided floppy) is not yet supported; the region must be
> de-interleaved into a copy, which cannot write back live
> ```
>
> (`_is_linear` is false for any multi-spec geometry, so sequential DSDs
> take the same copy path — both DSD layouts would be read-only.)

So modelling side 2 as a reserved region would make it **read-only** —
defeating Mark's entire use case, which is to *write* to it.

By contrast, the DFS class addresses a side natively as a separate surface
over the **whole** image buffer:

```python
DFS.from_buffer(reader.buffer(), double_sided_format, side=1)  # → disc.surface(1)
```

This writes back in place. Verified empirically: writing a title and a file
to `side=1` persisted to the file and left side 0 untouched.

**Conclusion:** the user-facing model is "two partitions," but the second
partition must **not** route through `region_reader`. It must open over the
whole image with a *surface index* threaded down to `DFS.from_buffer`.

## Proposed mechanism

### 1. `Partition` gains an optional surface index

`oaknut.filesystem.identification.Partition` is currently a logical-sector
run. Add:

```python
@dataclass(frozen=True)
class Partition:
    name: str
    start_sector: int
    num_sectors: int
    index: int = 0
    surface_index: int | None = None   # NEW: a whole-image surface, not a sector run
```

`surface_index is not None` marks a partition that is a *surface of the same
image* rather than a reserved sector-range region. The two are mutually
exclusive in practice: a reserved region has `surface_index is None` and
meaningful `start_sector`/`num_sectors`; a surface partition has
`surface_index` set and ignores the sector run.

### 2. The DFS probe advertises the second surface

When `probe()` proposes a double-sided geometry **and** the second surface
carries a valid catalogue (or is blank — see *Blank second side*), it
returns the side-0 identification as today, plus a contained identification
for side 1 with `surface_index=1`. Side 0 stays the host (the default).

This needs a probe path that does **not** go through `_recurse_regions`
(which is region-reader-based). Options:

- **(a)** The coordinator special-cases `surface_index`-bearing
  reserved entries: instead of `region_reader`, it re-probes that surface
  directly and attaches it as `contained`. Keeps probe declarative.
- **(b)** The DFS `probe()` builds and attaches the `contained`
  identification itself (it already has the geometry and the catalogue
  check), bypassing the coordinator's region recursion entirely.

Leaning **(b)** — it keeps the surface-vs-region fork inside the one
filesystem that has surfaces, rather than teaching the generic coordinator
about a DFS-shaped concept.

### 3. The mount opens a surface partition over the whole image

`mount.py:resolve_mount` currently does, for a contained partition:

```python
region_view = region_reader(reader, host.geometry, region.start_sector, region.num_sectors)
mount = filesystem.open(region_view, geometry)
```

For a `surface_index`-bearing partition it must instead open the **whole**
reader at the **double-sided** geometry, telling the filesystem which
surface. That requires the `open` contract to carry a surface:

```python
def open(self, reader, geometry, *, surface: int = 0) -> Mount: ...
```

`_DFSMount`/`_BaseDFS.open` then passes `side=surface` to `DFS.from_buffer`.
Other filesystems ignore the kwarg (default 0). Writability is preserved
because we open the live whole-image buffer, exactly as the verified
library path does.

### 4. Selector grammar accepts a bare drive number

`mount.py:_SELECTOR_RE` is `^([a-z][a-z0-9-]*(?:\.\d+)?):(.*)$`. Extend it to
also accept a bare integer drive number:

```python
^(\d+|[a-z][a-z0-9-]*(?:\.\d+)?):(.*)$
```

Disambiguation from a DFS directory named with a digit is clean: a selector
**must** be followed by a colon. `elite.dsd:2:$.PROG` → selector `2`, path
`$.PROG`; `elite.dsd:2.PROG` → no selector, path `2.PROG` (directory `2`,
file `PROG`). The outer compound split takes the first colon, so the inner
string the selector regex sees is `2:$.PROG`.

`Partition.selector` for a surface partition returns the **drive number**
(`"0"`, `"2"`) rather than the `name`/`index` form. Mapping: surface 0 →
drive 0, surface 1 → drive 2.

## User-facing surface

```sh
disc cp "drive-0.ssd:*" elite.dsd            # drive 0 (bare default)
disc cp "drive-0.ssd:*" elite.dsd:0:         # drive 0 (explicit)
disc cp "drive-2.ssd:*" elite.dsd:2:         # drive 2
disc ls   elite.dsd:2:$                       # list drive 2's $ directory
disc stat elite.dsd:2:                        # drive 2 disc-level info
disc title elite.dsd:2: "Compendium E side 2" # set drive 2's title
```

`disc stat elite.dsd` with no selector summarises drive 0 (unchanged). A
single-sided `.ssd` exposes only drive 0 — no second partition, and `:2:`
errors cleanly ("no such partition '2'; available: 0").

## Decisions to confirm

1. **Mechanism for surface partitions** — `Partition.surface_index` + an
   `open(..., surface=)` kwarg (proposed), versus a broader rework. Confirm
   the minimal shape.
2. **Probe wiring** — coordinator special-case (a) versus DFS builds its own
   `contained` (b). Proposed (b).
3. **Selector spelling** — bare drive numbers `0:`/`2:` (proposed, matches
   Acorn and Mark's guess). Also accept `drive0:`/`drive2:` aliases? Also
   keep a filesystem-name form (`acorn-dfs`/`acorn-dfs.1`) for scripting, or
   drop it as confusing?
4. **Blank / catalogue-less second side** — still expose drive 2 as an
   empty, writable, formattable partition (needed for Mark's
   build-from-two-SSDs flow), or only when a valid catalogue is present?
   Proposed: always expose drive 2 for a double-sided geometry, so it can be
   filled.
5. **`stat` / `ls` / partition listing** — should a bare `disc stat
   elite.dsd` (or a new listing) advertise that drive 2 exists, and how?
6. **Geometry ambiguity** — an 80T single-sided and a 40T double-sided image
   are the same byte length (`_propose_geometry` already flags this as an
   ambiguity). When the image is *interpreted* single-sided, there is no
   drive 2; when double-sided, there is. Does `:2:` force/assume the
   double-sided reading, and how does that interact with `--geometry`?
7. **Sequential vs interleaved DSDs** — both must work; the surface specs
   differ but `DFS.from_buffer(side=)` handles both. Confirm no extra
   surface for the user.
8. **Watford / Opus** — the same surface mechanism applies to any
   double-sided DFS-family geometry. Confirm scope includes them (likely
   free, since they share `_BaseDFS`).

## Test matrix (test-first)

The headline failing test to write first:

> Create a `.dsd`, `disc cp` files onto `:2:`, reopen, and assert drive 2
> holds them while drive 0 is untouched — and vice versa.

Then, per layer:

- `Partition.surface_index` round-trips; `selector` yields `0`/`2`.
- `_SELECTOR_RE` parses `2:$.PROG` as (selector `2`, path `$.PROG`) and
  `2.PROG` as (no selector, path `2.PROG`).
- DFS `probe()` on a double-sided image yields a contained surface
  partition; on single-sided, none.
- `resolve_mount('elite.dsd:2:$')` opens a **writable** mount over the live
  file (not a read-only de-interleaved copy).
- `disc stat elite.dsd:2:` reports drive 2's title/free space; bare
  reports drive 0.
- Clean error for `:2:` on a single-sided image (right exit code, no
  traceback).
- Interleaved and sequential DSDs both addressable.
- Watford double-sided image addressable via the same syntax.

## Docs

- `docs/dev/cli-design.md` — add drive-number addressing to the
  *Dual-partition addressing* section (it currently covers only `afs:` /
  `adfs:` filing-system prefixes).
- User-facing `disc` docs — a worked "assemble a DSD from two SSDs" example,
  which is exactly the workflow that surfaced the gap.

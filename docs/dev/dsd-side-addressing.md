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

Let a double-sided DFS image expose **both of its independent volumes**,
addressed by Acorn drive number, defaulting to drive 0 so nothing existing
regresses:

```sh
disc cp "drive-0.ssd:*" elite.dsd          # bare → drive 0 (default)
disc cp "drive-2.ssd:*" elite.dsd::2.$      # native Acorn path → second side
disc ls   elite.dsd::2.$
disc stat elite.dsd::2.$
```

This inherits the unqualified-means-drive-0 default, so existing
`elite.dsd:…` commands keep meaning drive 0 and nothing regresses.

The drive is addressed with **verbatim Acorn path syntax** rather than an
invented selector — see *Architecture: the filesystem owns the inner path*
below.

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

**Conclusion:** the second side must **not** route through `region_reader`.
It must open over the whole image with a *surface index* threaded down to
`DFS.from_buffer`. That points at a mount that spans the whole disc and
resolves the drive from the path — see the architecture below.

## Architecture: the filesystem owns the inner path

The least-surprising design is to let users type **exactly the Acorn path
they already know** — `:0.$.PLANETO`, `:2.Z.MYDATA`, `:0.D.MYPROG1` — and
make the **DFS extension responsible for interpreting the inner component**
of the compound path. The drive is not an oaknut-invented partition
selector; in real DFS it is an integral part of the path, written
`:drive.directory.filename`, and we honour that verbatim.

### The inner path is verbatim Beeb syntax

`parse_compound_path` already splits `OUTER:INNER` at the first colon and
hands the rest on unchanged. So:

| You type                       | Outer        | Inner (to the filesystem) | DFS reads          |
|--------------------------------|--------------|---------------------------|--------------------|
| `elite.dsd:$.PLANETO`          | `elite.dsd`  | `$.PLANETO`               | drive 0, `$.PLANETO` |
| `elite.dsd:D.MYPROG1`          | `elite.dsd`  | `D.MYPROG1`               | drive 0, `D.MYPROG1` |
| `elite.dsd::2.Z.MYDATA`        | `elite.dsd`  | `:2.Z.MYDATA`             | drive 2, `Z.MYDATA`  |
| `elite.dsd::0.$.PLANETO`       | `elite.dsd`  | `:0.$.PLANETO`            | drive 0, `$.PLANETO` |

The **inner component is exactly what you would type on a BBC Micro.** If
your Beeb path is drive-qualified it starts with a colon (`:2.Z.MYDATA`), so
the compound form has two colons: the first is oaknut's image delimiter, the
second is DFS's own drive colon — preserved by the existing parser, no
change needed. If your Beeb path is not drive-qualified (`$.PLANETO`,
`D.MYPROG1`), there is a single colon.

### Drive 0 by default — no "current drive" state

When the inner path carries no `:drive.` prefix, the DFS extension resolves
it against **drive 0**. This mirrors Acorn's default drive *as a default
only* — the CLI keeps **no** stateful "current drive" notion (no `*DRIVE`
analogue): each invocation is independent and an unqualified path is always
drive 0. So every existing `elite.dsd:$.X` command keeps meaning drive 0 and
nothing regresses.

The leading colon is what disambiguates a *drive* from a *directory* named
with a digit, exactly as on real hardware: `:2.FILE` is drive 2; `2.FILE` is
directory `2`. Because we honour the colon, the digit-directory shorthand
keeps working — no ambiguity, no special grammar.

### Which digit means the second side: forgiving "0 and non-zero"

A single image has exactly **two** sides, so there is nothing for a non-zero
drive digit to be ambiguous against. We exploit that to accept every
reasonable convention at once:

- `:0.` → side 0 (surface 0).
- `:N.` for **any non-zero** `N` (`1`, `2`, `3`, …) → the second side
  (surface 1).

This accommodates the Acorn-faithful reader who types `:2.` (drive 2 is the
back of drive 0 — see *Domain background*), the newcomer who reasonably
types `:1.`, and anyone who guesses `:3.`. All land on the one other side.
Acorn purists lose nothing; the uninitiated are not tripped up.

Open sub-question: what to **display** as the canonical drive number in
`stat` / listings — the Acorn-faithful `2` (this being an Acorn tool), or
the intuitive `1`. Input is forgiving either way; only the label is a
choice. (We might also *warn* on a wildly out-of-range digit like `:7.` to
catch a typo, while still resolving it to the second side.)

### A double-sided DFS mount spans the whole disc

Rather than mounting one surface and treating the other as a partition, a
double-sided DFS image mounts as **one disc with two surfaces**. The mount
parses the `:drive.` prefix and dispatches each operation to the right
surface, holding (and caching) a `DFS` per side over the **shared live
buffer** — both write back independently to disjoint sectors, as the two
`DFS.from_buffer(side=…)` instances already do (verified). Benefits:

- Native syntax falls out naturally — the drive lives in the path, where the
  filesystem parses it.
- No invented selector grammar, no `Partition.surface_index`, no
  `region_reader` for sides — the cross-cutting layers stay unchanged.
- Cross-drive copy within a single mount (`cp :0.A :2.B`) becomes possible,
  since one mount sees both surfaces.

What this needs:

1. **A filesystem-owned inner-path parse.** A hook on the `Mount`/filesystem
   contract by which the identified filesystem interprets the inner string —
   DFS strips an optional `:drive.` prefix to a surface index; ADFS/AFS parse
   their own `$`/`^`/`@` grammar. The generic cross-partition prefix
   (`afs:`/`adfs:` for an ADFS host with an AFS tail) stays a separate,
   coordinator-level dispatch that runs *first*; the chosen filesystem then
   parses the residual path. The two axes must be defined to compose
   cleanly (see decisions).
2. **A two-surface `_DFSMount`** for double-sided geometry: navigation,
   `stat`, `title`, free space etc. all key off the path's drive, defaulting
   to 0. For single-sided geometry it behaves exactly as today.
3. **`disc stat` / listing** to surface that drive 2 exists (the mount knows
   its surface count), so the second side is discoverable.

### Alternative considered (rejected): drive as a partition selector

The earlier sketch modelled the second side as a contained `Partition` with
a new `surface_index`, addressed by an invented `2:` selector
(`elite.dsd:2:$.PROG`), extending `mount.py:_SELECTOR_RE` to accept bare
digits. It works, but it invents non-Acorn syntax for something Acorn
already spells, and it splits drive handling across the generic mount layer
rather than the filesystem that owns the concept. Kept here only as the
fallback if filesystem-owned inner parsing proves too invasive.

## User-facing surface

```sh
disc cp "drive-0.ssd:*" elite.dsd                 # drive 0 (default)
disc cp "drive-2.ssd:*" elite.dsd::2.$             # drive 2, $ directory
disc ls    elite.dsd::2.$                          # list drive 2's $ directory
disc cat   elite.dsd::2.Z.MYDATA                   # read drive 2, dir Z, MYDATA
disc stat  elite.dsd::2.$                          # drive 2 disc-level info
disc title "elite.dsd::2.$" "Compendium E side 2"  # set drive 2's title
```

`disc stat elite.dsd` (unqualified) summarises drive 0. A single-sided
`.ssd` has only drive 0; an explicit `::2.` on it errors cleanly ("no drive
2 on a single-sided image").

## Decisions to confirm

Settling toward, in light of the discussion:

1. **Spelling — native Acorn path syntax (settling).** The inner component
   is verbatim Beeb syntax; the DFS extension parses the optional `:drive.`
   prefix. The invented `2:` partition selector is rejected.
2. **Drive digit — forgiving 0/non-zero (settling).** `:0.` → side 0; any
   non-zero `:N.` → the second side. Remaining sub-question: the canonical
   *display* drive number (Acorn-faithful `2` vs intuitive `1`), and whether
   to warn on out-of-range digits.
3. **Default drive — 0, stateless (settled).** Unqualified path is always
   drive 0; no "current drive" notion.

Still genuinely open:

4. **Filesystem-owned inner parsing — the contract.** What does the hook look
   like, and how does it compose with the existing generic cross-partition
   prefix (`afs:`/`adfs:`)? Does the prefix run first (coordinator picks the
   partition) and the chosen filesystem parse the residual, or do we unify
   them? This is the main architectural design task.
5. **Two-surface mount vs one-surface-plus-fallback.** Confirm the
   double-sided `_DFSMount` holds both surfaces over the shared buffer
   (enabling cross-drive `cp`), rather than the rejected
   per-surface-partition approach.
6. **Blank / catalogue-less second side** — expose drive 2 as an empty,
   writable, formattable side regardless of catalogue (needed for Mark's
   build-from-two-SSDs flow)? Proposed: yes, whenever the geometry is
   double-sided.
7. **`stat` / `ls` listing** — how should a bare `disc stat elite.dsd`
   advertise that a second side exists and is addressable?
8. **Geometry ambiguity** — an 80T single-sided and a 40T double-sided image
   are the same byte length (`_propose_geometry` flags this). An explicit
   `::N.` implies the double-sided reading; how does that interact with a
   forced `--geometry`, and what happens when the second side is unformatted
   garbage?
9. **Sequential vs interleaved DSDs** — both must work; `DFS.from_buffer
   (side=)` handles both. Confirm nothing extra surfaces to the user.
10. **Watford / Opus** — the same whole-disc mechanism should cover any
    double-sided DFS-family geometry, since they share `_BaseDFS`. Confirm
    scope.

## Test matrix (test-first)

The headline failing test to write first:

> Create a `.dsd`, `disc cp` files onto `::2.$`, reopen, and assert the
> second side holds them while drive 0 is untouched — and vice versa.

Then, per layer:

- Compound-path round-trips: `elite.dsd::2.Z.MYDATA` → outer `elite.dsd`,
  inner `:2.Z.MYDATA`; `elite.dsd:$.X` → inner `$.X`.
- DFS inner-path parse: `:2.Z.MYDATA` → (side 1, `Z.MYDATA`); `:0.$.X` →
  (side 0, `$.X`); `$.X` → (side 0, `$.X`); forgiving `:1.` and `:3.` both →
  side 1; digit-directory shorthand `2.FILE` → (side 0, dir `2`, `FILE`).
- A double-sided `_DFSMount` reads/writes each side independently over the
  shared buffer; both persist; neither corrupts the other's interleave.
- `resolve_mount('elite.dsd::2.$')` yields a **writable** mount over the live
  file (not a read-only de-interleaved copy).
- `disc stat elite.dsd::2.$` reports the second side's title/free space; bare
  reports drive 0.
- Clean error for `::2.` on a single-sided image (right exit code, no
  traceback).
- Interleaved and sequential DSDs both addressable.
- Watford double-sided image addressable via the same syntax.

## Docs

- `docs/dev/cli-design.md` — add drive-number addressing to the
  *Dual-partition addressing* section (it currently covers only `afs:` /
  `adfs:` filing-system prefixes).
- User-facing `disc` docs — a worked "assemble a DSD from two SSDs" example,
  which is exactly the workflow that surfaced the gap.

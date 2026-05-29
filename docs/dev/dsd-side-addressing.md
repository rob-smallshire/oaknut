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

### Three layers, three owners

A fully-qualified compound path peels in three stages, each owned by the
layer that understands it:

```
image.dsd : dfs : :2.$.MYPROG
└─ outer ─┘ └ A ┘ └─── B ───┘
```

| Stage | What it selects | Owner | Status |
|---|---|---|---|
| outer `:` | the host image file | `parse_compound_path` (cli_paths) | exists |
| **A** `partition:` | which filing system / partition in the image (`adfs:`, `afs:`, `afs.1:`, `dfs:`) | generic `split_selector` (mount) | exists |
| **B** `:drive.path` | the volume *within* that filesystem, then the path | **the filesystem itself** | new |

Stage A is the cross-partition axis (an ADFS host with an AFS tail). Stage B
is intra-filesystem and **filesystem-specific** — only DFS has drives. The
two compose by sequence, not negotiation: A runs first and picks the
filesystem; that filesystem then owns everything to the right.

Verified empirically against the current code: `image.dsd:dfs::2.$.MYPROG`
already splits to outer `image.dsd`, selector `dfs`, residual `:2.$.MYPROG`
with **no parser change** — the partition delimiter's colon and the DFS
drive's colon sit adjacent as `::`. (Today the selector must be the
registered name `acorn-dfs`; a friendly `dfs:` alias is a small
sub-decision. For a single-partition DSD the prefix is optional, so
`image.dsd::2.$.MYPROG` suffices.)

### The new hook: the filesystem splits its own volume

The drive must be known **before** the mount opens, because — see below —
the capability model makes a mount represent exactly one volume. So the
contract is a small method on the filesystem, called by `resolve_mount`
after the partition is chosen:

```python
def split_volume(self, inner_path: str, geometry: Geometry) -> tuple[int, str]:
    """Split a leading volume token from *inner_path*.

    Returns ``(surface_index, residual_path)``. The default takes
    surface 0 and the whole path — most filesystems have no notion of a
    sub-volume. DFS overrides it to parse the Acorn ``:drive.`` prefix:
    drive 0 -> surface 0, any non-zero drive -> surface 1 (when the
    geometry is double-sided), erroring on a drive for a single-sided
    image. ADFS/AFS use the default — ADFS-L spans both physical
    surfaces as one logical volume, so it exposes no drive.
    """
    return 0, inner_path
```

`resolve_mount` then opens that surface and sets the residual as the
in-partition path:

```python
surface, residual = filesystem.split_volume(in_path, geometry)
mount = filesystem.open(region_view, geometry, surface=surface)   # open gains surface=
return ResolvedMount(mount, path=residual, …)
```

`open` gains a `surface: int = 0` kwarg; `_BaseDFS.open` threads it to
`DFS.from_buffer(reader.buffer(), disc_format, side=surface)` — opening the
chosen side over the **whole live buffer**, so writes persist (verified).
Every other filesystem ignores the kwarg.

### Why one volume per mount, not a two-surface mount

The capability protocols (`Titled`, `Bootable`, `FreeSpace`, `Sized`,
`FreeMap`, `Validatable`, `Compactable`) are **mount-global** — `title`,
`boot_option`, `free_bytes()` take no path. But each DFS side is an
independent volume with its *own* title, boot option, free space and
catalogue. A mount spanning both surfaces could not answer "drive 2's
title" through these property-based capabilities without inventing a
per-drive variant of every one of them.

Resolving the drive at open time avoids that entirely: the mount **is** one
drive's volume, so every capability is unambiguously that drive's, and the
capability model is untouched. The cost is that a single mount sees only one
side — but **cross-drive `cp` still works**, because `cp` takes two compound
paths and resolves a mount for each (`cp elite.dsd::0.$.A elite.dsd::2.$.B`
→ a read-only mount of drive 0 and a writable mount of drive 2). That is
also the *correct* mental model: the two sides are independent volumes, so
copying between them is a copy between volumes, not a move within one.

What this needs, in total:

1. `Filesystem.split_volume(inner_path, geometry)` — new, default
   `(0, inner_path)`; DFS overrides.
2. `Filesystem.open(reader, geometry, *, surface=0)` — one new kwarg;
   only DFS reads it.
3. `resolve_mount` calls `split_volume`, opens the surface, sets the
   residual path.
4. `disc stat` / listing surfaces that a second side exists, so it is
   discoverable.

No change to `Identification`, `Partition`, the coordinator, `_SELECTOR_RE`,
or any capability protocol.

### Alternative considered (rejected): drive as a partition selector

The earlier sketch modelled the second side as a contained `Partition` in
the identification tree with a new `surface_index`, addressed by an invented
`2:` selector (`elite.dsd:2:$.PROG`), extending `mount.py:_SELECTOR_RE` to
accept bare digits. It invents non-Acorn syntax for something Acorn already
spells, and it pushes a DFS-only concept (drives) into the generic
identification and selector layers that every filesystem shares. The
`split_volume` contract above keeps the drive entirely inside the DFS
extension and leaves the shared layers untouched — so this is rejected.
(Note the *surface* still reaches `open` — but via the filesystem's own
path parse, not a partition in the identification tree.)

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

Settling (this round):

4. **Inner-parse contract — `split_volume` (settling).** Three-layer peel:
   outer file → generic `partition:` selector → filesystem-owned
   `:drive.path`. The new `Filesystem.split_volume(inner_path, geometry)`
   returns `(surface_index, residual_path)`, default `(0, inner_path)`; DFS
   overrides. The partition prefix runs first and picks the filesystem; that
   filesystem then owns the residual. No change to identification, the
   coordinator, `Partition`, or `_SELECTOR_RE`.
5. **One volume per mount (settling).** The drive resolves at open time
   (`open(..., surface=)`), so a mount represents exactly one side's volume
   and the mount-global capability protocols stay untouched. Cross-drive
   `cp` uses two compound paths (two mounts) — correct, since the sides are
   independent volumes.

Still genuinely open:

5a. **`dfs:` alias.** Accept `dfs:` as a friendly alias for the `acorn-dfs`
    (and `watford-dfs`?) partition selector, or require the registered name?
    Optional for a single-partition DSD regardless.
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

# AFS on-the-wire specification

Status: living document. Seeded from `L3V126/Uade01.asm` + `Uade02.asm`
in phase 0 of `docs/afs-implementation-plan.md`. Subsequent phases will
extend this document as they consult further ROM modules.

**When this document disagrees with either `wfsinit.md` or Beebmaster's
PDF, the ROM is authoritative and this document reflects the ROM.**

All citations are to files under `/Users/rjs/Code/L3V126/` unless noted.

## Conventions

- **Byte order**: multi-byte integers are stored **little-endian** (LSB
  first) unless explicitly noted otherwise.
- **Sector size**: 256 bytes. `Uade01.asm:254` — `BLKSZE = &100`.
- **Sector address (SIN) width**: 24-bit. The on-disc address space is
  addressed with 3-byte values throughout.
- **Name length**: object names are up to 10 characters, space-padded
  for storage. `Uade02.asm:120` — `NAMLNT = &A`.
- **Root name**: `$`. `Uade02.asm:122` — `ROOT = '$'`.
- **Path separator**: `.`. `Uade02.asm:119` — `SEPART = '.'`.

## Constants

| Constant | Value | Meaning | Source |
|---|---|---|---|
| `BLKSZE` | `&100` (256) | Bytes per sector | `Uade01:254` |
| `NAMLNT` | `&A` (10) | Max text name length | `Uade02:120` |
| `MAXPW` | `6` | Max password length | `Uade02:16` |
| `MAXID` | `10` | Max single user ID length | `Uade02:17` |
| `MAXUNM` | `21` | Max user IDs plus dot (for `group.user`) | `Uade02:18` |
| `MAXUSE` | `80` | Max users | `Uade01:204` |
| `MAXDRV` | `5` | Max drives per file server | `Uade01:205` |
| `MAXDIR` | `6656` (26 sectors) | Max directory size in bytes | `Uade02:123-124` |
| `BASEYR` | `81` | Base year for FS dates | `Uade01:207` |
| `DNAMLN` | `&10` (16) | Disc name length | `Uade02:250` |
| `SZOFF` | `&F6` | ADFS sector-0 offset at which the AFS info-sector pointer lives (both copies, in sector 0 and sector 1) | `Uade02:203` |

## Access byte (1 byte, in directory entries)

From `Uade01.asm:257-275`:

| Bit | Constant | Meaning |
|---|---|---|
| 0 | `READAC = 1` | Public read access |
| 1 | `WRITAC = 2` | Public write access |
| 2 | — | Owner read access |
| 3 | — | Owner write access |
| 4 | `LOCKED = &10` | Locked (cannot be deleted/overwritten) |
| 5 | `TYPE = &20` | Object is a directory (`TYPDIR`) if set, else file (`TYPFIL`) |
| 6-7 | — | Unused in the on-disc access byte |

Masks:

| Constant | Value | Meaning |
|---|---|---|
| `ACCMSK` | `&1F` | Mask covering bits 0–4 (locked + all four R/W bits) |
| `TLAMSK` | `&3F` | Type + access (bits 0–5) |
| `RWMSK`  | `&F`  | Four R/W bits only (owner + public) |

Predefined combinations referenced in the ROM:

| Constant | Value | Meaning |
|---|---|---|
| `ACCDEF` | `&0C` | Default: Owner R+W, public none (bits 2, 3) |
| `RDWRAC` | `&03` | Public R+W (bits 0, 1) |
| `RWLACC` | `&13` | Public R+W + locked (bits 0, 1, 4) |

Note that `Uade01:262` also defines `OWNER = &40` as a flag used when
checking authorisation (caller is owner) — this is **not** a bit in the
on-disc access byte.

The Beebmaster PDF and WFSINIT tables confirm the bit layout above.
Acorn Application Note 75 documents a different layout; the ROM and
Beebmaster's observations from real discs are the correct references.

## User status byte (1 byte, in passwords file entries)

From `Uade01.asm:263-268`:

| Bit | Constant | Meaning |
|---|---|---|
| 0-1 | — | Boot option: 0 = off, 1 = load, 2 = run, 3 = exec |
| 2-4 | — | Unused |
| 5 | `LOCKPV = &20` | Lock user privileges (e.g. prevent password change) |
| 6 | `SYSTPV = &40` | System privilege |
| 7 | `INUSE = &80` | Entry in use (clear = entry is ignored) |

`NTSYST = &9F` is the complement of `SYSTPV` used for bit-clearing.

## Info sector (sector zero of the AFS region)

From `Uade02.asm:190-205`. This is the on-disc layout of each of the
two redundant copies of the "disc info" sector (the sectors WFSINIT
writes at `sec1%` and `sec2%`).

| Offset | Size | ROM label | Meaning |
|---|---|---|---|
| 0 | 4 | `MPDRNM` | Magic bytes `'AFS0'` |
| 4 | 16 | `MPSZNM` | Disc name, space-padded |
| 20 | 2 | `MPSZNC` | Number of cylinders per disc |
| 22 | 3 | `MPSZNS` | **Number of sectors per disc (24-bit)** |
| 25 | 1 | `MPSZDN` | Number of discs (almost always 1) |
| 26 | 2 | `MPSZSC` | Sectors per cylinder |
| 28 | 1 | `MPSZSB` | Size of bit map in sectors (almost always 1) |
| 29 | 1 | `MPSZAF` | Addition factor — added to get the next physical disc number (multi-drive) |
| 30 | 1 | `MPSZDI` | Drive increment — step to the next logical drive (multi-drive) |
| 31 | 3 | `MPSZSI` | SIN of the root directory |
| 34 | 2 | `MPSZDT` | Date (packed 16-bit; see §Date encoding) |
| 36 | 2 | `MPSZSS` | Start cylinder (first cylinder of the AFS region) |

**Resolving a source discrepancy.** `wfsinit.md` §6 and Beebmaster's PDF
disagreed about bytes 29 and 30. The ROM (above) settles it: byte 29 is
the addition factor (physical drive step), byte 30 is the drive
increment (logical drive step). Beebmaster's "byte 30 unused" is wrong.

**Byte 38 (floppy/Winchester flag).** Beebmaster's PDF documents a
media flag at byte 38. The ROM's in-memory struct definition for sector
zero ends at byte 37 (the end of `MPSZSS`), with no explicit field for
byte 38. The ROM does not appear to read or write byte 38 in Uade01/02,
so it is presumed either unused or written by code we have not yet
examined. Phase 15 (partition) should write `0` there to be safe and
phase 2 tests should not require it to decode.

The max number of sectors that this info block can describe is
`2^24 = 16,777,216 sectors = 4 GiB` (`MPSZNS` is 24 bits), but the
L3FS SCSI address encoding (21-bit sector address per drive × 256 B)
caps a single physical drive at 512 MiB, and period Winchesters were
≤20 MiB. Plan on ~20 MiB when sizing defaults.

## Directory header (17 bytes, at offset 0 of a directory object)

From `Uade02.asm:77-83`:

| Offset | Size | ROM label | Meaning |
|---|---|---|---|
| 0 | 2 | `DRFRST` | Pointer (byte-offset from start of directory) to the first in-use entry |
| 2 | 1 | `DRSQNO` | **Master sequence number (leading copy)** |
| 3 | 10 | `DRNAME` | Directory name, space-padded |
| 13 | 2 | `DRFREE` | Pointer to the first free entry |
| 15 | 2 | `DRENTS` | Number of entries the directory is sized for |
| 17 | — | `DRSTAR` | First entry begins here |

The **trailing** master-sequence-number byte is stored at the last byte
of the directory object. The ROM comment at `Uade02:68-75` states:

> A one byte sequence number (incremented when writing a dir to disc)
> brackets a directory. The leading sequence number goes at byte offset
> 2 and the trailing sq no is the last byte of a dir. These sq nos are
> used to detect dirs which have not been written to disc completely —
> note dirs can be multi-sector objects. Sq nos are checked whenever a
> dir is loaded.

If `byte[2] != byte[last]`, the server raises **`DRERRB = MODDIR + 2 =
&42` ("broken directory")** — see the error codes table below.

**Directory size formula.** `MAXDIR = HI(DRSTAR + 255 × DRENSZ) + 1) × &100`
= `HI(17 + 255 × 26) + 1) × 256` = `HI(6647) + 1) × 256` = `(25 + 1) ×
256` = **6656 bytes (26 sectors)**. A directory with exactly the
declared number of entries occupies `17 + N × 26 + 1` bytes (the `+ 1`
is the trailing sequence-number byte); this is rounded up to a whole
number of sectors for on-disc storage.

The server may grow a directory up to this maximum. *The growth
strategy itself is not described in Uade01/02 — it lives in DIRMAN
(`Uade0C`–`Uade0E`), to be documented in phase 7.*

## Directory entry (26 bytes, repeated)

From `Uade02.asm:85-95`:

| Offset | Size | ROM label | Meaning |
|---|---|---|---|
| 0 | 2 | `DRLINK` | Pointer to next entry in list (0 = end of list) |
| 2 | 10 | `DRTITL` | Text name, space-padded |
| 12 | 4 | `DRLOAD` | Load address (LE) |
| 16 | 4 | `DREXEC` | Execute address (LE) |
| 20 | 1 | `DRACCS` | Access byte (see §Access byte) |
| 21 | 2 | `DRDATE` | Date of creation (packed) |
| 23 | 3 | `DRSIN` | System Internal Name (SIN) of the object, 24-bit LE |
| — | — | `DRENSZ` | **= 26 bytes total** |

Two linked lists are maintained in the header: `DRFRST` heads the
in-use list (kept in alphabetical order by the link chain, not by
physical slot position), and `DRFREE` heads the free-slot list. Both
use `DRLINK` as the next-pointer. When inserting a new entry, the
server pops a slot from the free list and splices it into the in-use
list at the alphabetical position.

## Passwords file entry (31 bytes, repeated)

From `Uade02.asm:133-141`:

| Offset | Size | ROM label | Meaning |
|---|---|---|---|
| 0 | 20 | `PWUSID` | User ID (`MAXUNM - 1 = 20` bytes). May be `group.user` with a `.` separator, or just `user`. Terminated with CR (`&0D`) if shorter than the field. |
| 20 | 6 | `PWPASS` | Password (`MAXPW = 6` bytes). Terminated with CR if shorter. |
| 26 | 4 | `PWFREE` | Free space remaining (`UTFRLN = 4` bytes, 32-bit LE) |
| 30 | 1 | `PWFLAG` | Status byte (see §User status byte) |
| — | — | `PWENSZ` | **= 31 bytes total** |

The passwords file itself is an AFS object with access byte `&00` (no
public or owner access), located at `$.Passwords`. WFSINIT creates it
with initial capacity of one sector (~8 users). It must always be a
whole number of sectors or the file server refuses to mount.

Interesting quirk from `Uade01:37`:

> `URERRB = EXTER0 - 8 ; USERTB FULL`

and `Uade02:37`:

> `USRLIM = MAXUSE + 1; MAX 40 USERS FOR NOW **`

The comment says "40 users" but `MAXUSE = 80`. Take this as the authoritative
upper bound on users per disc: **80**. The "40" comment is stale.

## Map sector (JesMap)

`Uade02` holds the MAPTB (in-memory per-disc map table, `Uade02:228-247`)
describing what the server tracks per-disc at run time:

- `MPDCNO` (2 bytes): disc number
- `MPNOCY` (2 bytes): number of cylinders
- `MPSECS` (3 bytes): sectors per disc (24-bit)
- `MPDSCS` (1 byte): number of discs
- `MPSPCY` (2 bytes): sectors per cylinder
- `MPBMSZ` (1 byte): bit map size in sectors
- `MPADFT` (1 byte): addition factor
- `MPDRNC` (1 byte): drive increment
- `MPRTSN` (3 bytes): SIN of root directory
- `MPRTDT` (2 bytes): root date
- `MPSCYL` (2 bytes): start cylinder
- `MPSZCY` (1 byte): size in bytes of cylinder bit map

### Map block layout (on disc and in memory)

The *map block pointer block* header at `Uade02:313-334` is both the
**in-memory descriptor** of a loaded map block *and* the on-disc byte
layout once the 6-byte ASCII magic has been replaced by the block's
own SIN/BLKNO. The fields are:

| Offset | Size | Label   | Meaning |
|-------:|-----:|---------|---------|
|  0 | 3 | `BLKSN`  | On disc: first 3 bytes of `'JesMap'` magic. In memory after read: the SIN this map block was loaded from. |
|  3 | 3 | `BLKNO`  | On disc: last 3 bytes of `'JesMap'` magic. In memory: the block's ordinal number / drive number (not used on the wire). |
|  6 | 1 | `MBSQNO` | Leading master sequence number. |
|  7 | 1 | `MGFLG`  | Reserved flags byte (always zero in L3V126). |
|  8 | 2 | `BILB`   | **Bytes in last (data) block — 16-bit LE**. Only the final map block in a chain carries a meaningful value; intermediate blocks leave it stale. Zero means "last data sector is fully used" (i.e. add a full 256 bytes). `Uade13:573-595` (`MPGSFN`). |
| 10 | 245 | `MBENTS` | Body: up to 49 five-byte extent slots, `ENSZ = 5` (3-byte start sector LE + 2-byte length LE). |
| 255 | 1 | trailing `MBSQNO` | Must equal the leading copy; mismatch raises `DRERRB` / "broken directory". `Uade11` on write, `Uade02:332` (`LSTSQ`). |

Constants from `Uade02:329-334`:
- `ENSZ = 5`
- `MXENTS = 49`
- `LSTENT = MBENTS + (MXENTS - 1) * ENSZ = 10 + 48*5 = 250`
- `LSTSQ = 255`
- `BTINBK = 256`

The magic is written by `Uade10.asm:229-236` (`MPCRSP`), which copies
the six-byte literal ``MPBLTX EQUB "paMseJ"`` onto disc with an index
that runs from 5 down to 0, producing the bytes `J`, `e`, `s`, `M`,
`a`, `p` in normal order on the wire.

### Chained map blocks

**The 49th extent slot (index 48, at `LSTENT = 250`) is reserved as
the chain pointer, not a data extent**. When a file acquires a 49th
extent, MAPMAN allocates a new map block and overwrites slot 48 of
the *old* map block with the new block's SIN (3 bytes) plus length 1
(2 bytes). The data extent that would have gone there is placed into
slot 0 of the new map block, and the chain continues from there.

Source: `Uade12.asm:187-227` (`MKRLN` / `ALBLK` path) stores `(newblock_SIN, 1)` at
`MPMBPT + LSTENT` and writes the old block back. The reader side in
`Uade13.asm:470-533` (`MPGTSZ`/`MPGSMB`) walks extent slots starting
at `MBENTS`, detects zero starts as end-of-data, and compares the
current slot offset against `LSTENT`: if a non-zero entry is found at
or beyond `LSTENT`, the entry's 3-byte start field is treated as the
SIN of the next map block and the walker jumps via `MPGSNX` into
`RDMPBK` on that SIN.

This has several important consequences for any parser:

1. **Only 48 data extents fit in one map block.** The 49th slot can
   never hold a data extent — writing one there would be
   indistinguishable from a chain pointer on read.
2. **Chains are singly-linked forward lists.** There is no back
   pointer; each block only knows its successor. `BLKSN` / `BLKNO`
   are populated from whatever sector the server happened to read,
   not from the bytes on disc.
3. **Chain termination is by zero start sector.** Either a zero
   entry anywhere in slots 0..47, or a zero entry at slot 48,
   terminates the chain. There is no explicit "last block" flag.
4. **`MBSQNO` is a corruption check, not a chain ordinal.** Leading
   (byte 6) and trailing (byte 255) copies must agree. There is no
   relationship between the sequence numbers on adjacent blocks in
   a chain; each is its own independent counter.
5. **`BILB` is only meaningful on the final block in a chain.**
   Intermediate blocks carry stale values from whenever they were
   last written, and `MPGSFN` at `Uade13:573-595` only reads it
   after `MPGTSZ` has reached end-of-chain via `MPGSGB`.

The Python read path in `oaknut.afs.map_sector` therefore needs:

- A parser that returns extents from slots 0..47 only, plus an
  optional `next_sin` from slot 48.
- A chain walker (owned by the `AFS` handle, since it needs to
  dereference SINs back to sector reads) that calls the parser
  repeatedly to produce a flat list of data extents plus the final
  block's `BILB`.
- `ExtentStream` stays byte-addressable over the flattened extents
  unchanged.

## Bit map

`Uade01`/`Uade02` give:
- `MPBMSZ` (in `MAPTB`): size of bit map in sectors, usually 1.
- `MPSZCY` (in `MAPTB`): size in bytes of the cylinder bit map.
- `NOBTMP = 5` (Uade02:242): number of bit-map cache blocks.
- `MPVAL = &FF` (Uade02:225): offset of the "next bitmaps valid" flag.

Bit 1 = free, bit 0 = allocated, per the PDF and WFSINIT. The bit
ordering within a byte (high sector first) is documented in the PDF,
byte 0 covering the first 8 sectors of the cylinder. This file will be
extended with the authoritative bit order after phase 3 cross-checks
it against MBBMCM.

## FS error codes

Selected errors the file server returns over Econet. The full list is
in `Uade01.asm:34-149`. These are the values we want to carry on our
own `AFSError.fs_error_code` attribute for symmetry.

| Constant | Value | Meaning |
|---|---|---|
| `URERRA` | `&BF` | M/C number not in usertb |
| `URERRB` | `&B8` | Usertb full |
| `URERRD` | `&14` | Object not a directory |
| `URERRE` | `&AE` | User not logged on |
| `DRERRA` | `&CC` | Invalid separator in file title |
| `DRERRB` | `&42` | **Broken directory** (master-seq mismatch) |
| `DRERRC` | `&D6` | Object not found |
| `DRERRD` | `&BE` | Object not a directory |
| `DRERRE` | `&BD` | Insufficient access |
| `DRERRG` | `&C3` | Dir entry locked |
| `DRERRI` | `&C2` | Object in use (open) |
| `DRERRJ` | `&B4` | Directory not empty |
| `ATERRA` | `&21` | Cannot find password file |
| `ATERRB` | `&BC` | UserID not found in password file |
| `ATERRC` | `&BB` | Incorrect password |
| `ATERRD` | `&BA` | Insufficient privilege |
| `ATERRH` | `&B2` | Password file full |
| `RDERRB` | `&DE` | Invalid handle |
| `RDERRJ` | `&DF` | End of file |
| `MPERRA` | `&C8` | Disc number not found |
| `MPERRB` | `&C6` | Disc space exhausted |
| `MPERRD` | `&54` | Disc not a file server disc |
| `MPERRK` | `&D6` | Disc name not found |
| `MPERRN` | `&5C` | Insufficient user free space |
| `DCERRE` | `&C9` | Disc protected |
| `DCERRF` | `&C7` | Unrecoverable disc error |

`MODXXX` constants are module base tags, added to a small within-module
error number. `EXTER0 = &C0` is the base for "external (BBC machine)"
errors. Error numbers above `&C0` are generally meaningful to clients;
lower numbers are server-internal.

## Date encoding (packed 16-bit)

Details not in Uade01/02 directly. `BASEYR = 81` and `YRHUND = 20`
(`Uade01:207-208`) tell us: base year is 1981, 21st-century years get
`100` added. Packing formula from `wfsinit.md` §3:

```
encoded = ((year - 81) * 4096) + (month * 256) + day + ((year - 81) AND &F0) * 2
```

To be cross-checked against the ROM in phase 2 when the info-sector
date round-trip is tested.

## Gaps to be filled in later phases

These structures/algorithms are not yet documented here because they
live in ROM modules beyond `Uade01/02`. Each will be added during its
phase.

- **Directory growth strategy** — handled at the MAPMAN layer via
  `MAPMAN.CHANGESIZE` (`Uade0E.asm:1222` `CHZSZD`): DIRMAN asks MAPMAN
  to grow the underlying object, then reformats the newly-allocated
  tail as free slots threaded onto the free list. Phase 7 for the
  read path (large directories read automatically once chained maps
  work); phase 10 for the write path.
- **Allocation policy** — MBBMCM, phase 8.
- **Extend / truncate semantics** — RNDMAN (`Rman01`–`Rman05`) + MAPMAN,
  phase 12.
- **Quota credit/debit points** — AUTMAN (`Uade0F`) + USRMAN (`Uade06`),
  phase 14.

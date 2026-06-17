# The Acorn ROM Filing System (ROMFS) on-ROM format

This document describes the byte layout of a ROMFS paged ROM. It is the
reference for the parser and serialiser in this package.

ROMFS is documented only sparsely in primary Acorn material. The layout
here is reconstructed from the OS reader itself plus working generators,
and cross-checked against the *New Advanced User Guide* (NAUG) service-ROM
template:

- **Acorn MOS disassembly** — the OS Tape and ROM Filing System source,
  the authoritative reference for the *read* state machine.
  <https://tobylobster.github.io/mos/mos/S-s18.html>
- **"Code when loading from ROM"** — a control-flow diagram of the MOS
  load-from-ROM routine, naming the state machine and its routines:
  `docs/dev/manuals/LoadFromROM.pdf` (in this repo).
- **Bruce Smith, *Advanced Sideways RAM User Guide*, ch. 4** — the `*HELP`
  (`&09`) service handler; the created-ROM help routine follows it (with
  register preservation added). Notes in the Acornaeology library at
  `library/books/advanced_sideways_ram_user_guide/notes/chapter_4_the_help_service.md`.
- **"Sideways ROM authoring notes"** — the most complete single reference,
  compiling the New Advanced User Guide, Bruce Smith's *BBC Micro ROM
  Book* and the *Electron Advanced User Guide*. Covers the paged-ROM
  header bit-by-bit, every MOS service call, and the RFS block format and
  `&0D`/`&0E` handler with worked 6502. In the sibling Beebium repo at
  `docs/manuals/sidewrom.pdf`. It corroborates §1–§3 below field-for-field
  and is the source for the service-call interface in §2.10.
- **New Advanced User Guide**, §17.5 (Acorn Computers) — the original
  published reference for the `*ROM` filing system, and the basis for the
  byte tables below: the on-ROM data format, the `&0D`/`&0E` service calls,
  and a complete worked `&0D`/`&0E` handler in BBC BASIC. In-repo extract at
  `docs/dev/manuals/ROMFS-Advanced-Guide.pdf`. Our created handler descends
  from this example. **Its printed handler has a defect**: it masks the
  serial-ROM scan number with `AND #&F`, so a ROM in sideways socket 0
  re-claims itself past the `&2B` end marker and loops `*CAT` forever. The
  genuine Acornsoft ROMs guard this with `CMP #&10` / `BCS`; our created
  handler does too (see §2.10).
- **MakeRFS** — J.G. Harston's 6502 builder, with a fast loader.
  <https://mdfs.net/Software/BBC/ROMFS/MakeRFS>
- **UEF2ROM** — converts UEF cassette images to Acorn Electron ROM
  cartridges (the same ROMFS format).
  <https://github.com/stardot/UEF2ROM>
- Stardot discussion: <https://stardot.org.uk/forums/viewtopic.php?t=23135>

> **Verification status.** The paged-ROM header, the per-file block field
> layout, and the marker-byte / flag-bit semantics below are corroborated
> by *both* the MOS reader disassembly and the New Advanced User Guide, and
> are high-confidence. The items still marked **(confirm against images)**
> are the few that the OS reader does not pin down — chiefly where the
> filing-system data starts within a given generator's ROM, and multi-bank
> spanning — and should be checked against the reference Electron/BBC ROM
> images before the parser is finalised.

## 1. The paged-ROM container

A ROMFS ROM is an ordinary Acorn *paged ROM* (sideways ROM or cartridge),
mapped at `&8000`–`&BFFF` (16 KiB) — 8 KiB ROMs occupy `&8000`–`&9FFF`.
It begins with the standard paged-ROM header, then a service-call handler,
then the ROM filing-system data.

### 1.1 Paged-ROM header

From `handlesvc.asm` (offsets are absolute, ROM mapped at `&8000`):

| Offset | Bytes | Field | Notes |
|-------:|------:|-------|-------|
| `&8000` | 3 | Language entry | `JMP language` on a language+FS ROM, or `00 00 00` if none |
| `&8003` | 3 | Service entry | `JMP service` (`4C lo hi`) |
| `&8006` | 1 | ROM type | bitfield — see below |
| `&8007` | 1 | Copyright offset | offset, *relative to ROM start*, of the `00` byte before `(C)` |
| `&8008` | 1 | Binary version | a single version byte |
| `&8009` | n+1 | Title | ASCII title string, NUL-terminated |
| … | m | Version string | printable version text (may be empty) |
| … | 1 | `00` | leading NUL of the copyright field (pointed at by `&8007`) |
| … | k | Copyright | ASCII copyright string; **must begin `(C)`** |
| … | 1 | `00` | end of paged-ROM header |

The copyright string starting with `(C)` is mandatory for a valid Acorn
paged ROM, and the byte at `&8007` must point at the `00` immediately
preceding it. These two facts give a strong structural check when
identifying a ROMFS image.

**ROM type byte (`&8006`) bits:**

| Bit(s) | Meaning |
|-------:|---------|
| 7 | Service entry present (set by every ROMFS ROM; `probe()` tests this) |
| 6 | Language entry present |
| 5 | Has a second-processor (Tube) relocation address |
| 4 | Supports Electron firmkeys (`KEY+FUNC` / `KEY+CAPS`) |
| 3–0 | CPU type: `0000` 6502 BASIC, `0010` 6502 (not BASIC), `0011` 68000, `1000` Z80, `1001` 32016, `1011` 80186, `1100` 80286, `1101` ARM |

So the corpus's `&C2` is `service + language + 6502` and Zalaga's `&82`
is `service + 6502` (no language). Identify on **bit 7**, never the whole
byte.

> **Observed on the reference corpus** (six Acornsoft Electron cartridges,
> §6). The ROM type byte is **`&C2`** — service *and* language entry
> present (the cartridges are language ROMs too), so `probe()` must test
> *bit 7* rather than match `&82` (which is what a service-only ROM emits).
> Every cartridge carries the generic header title
> `"ROM Cartridge"`, version `&01`, and copyright `(C) 1984 Acornsoft` at
> offset `&18`. The *filing-system* title is **not** this header title; it
> is the `*…*`-wrapped title block (§2.5). So treat the header title as
> incidental and read the displayed disc title from the title block.

### 1.2 Service handler

Between the header and the filing-system data sits the 6502 service
handler that responds to OSRDRM-style byte reads (`handlesvc.asm`
implements service calls `&0D` *initialise filing system* and `&0E` *read
byte*). The parser does not need to interpret this code; it only needs to
know that the filing-system data begins *after* it. In the New Advanced
User Guide layout the data starts at a fixed offset that depends only on
the lengths of the title,
version and copyright strings:

```
DATA_OFFSET = 0x805D + len(version_str) + len(title) + len(copyright)
```

`0x805D` is the size of the header plus service handler with empty title,
version and copyright. (Images created by *this* package use a handler six
bytes longer — see the socket-0 note in §2.10 — so their empty-header anchor
is `0x8063`. The parser never relies on either: it scans for the first
CRC-valid block.)

> **Do not trust a fixed offset.** On the reference corpus the data start
> *varies by ROM* — `&80BB` for most, `&829C` for Countdown To Doom —
> because the hand-written 6502 handler differs in length. The robust
> approach, confirmed across all six images, is to **scan forward from the
> header for the first `&2A` whose block header CRC validates**, and treat
> that as the start of the filing-system data. The `DATA_OFFSET` formula
> above applies only to ROMs a generator lays out that way.

## 2. The filing-system data: a chain of CFS blocks

After the header/handler comes the ROM filing-system data: a sequence of
files, each a chain of one or more blocks in **Cassette Filing System**
format, terminated by an end-of-filesystem marker.

### 2.1 Marker bytes

| Byte | Char | Meaning |
|-----:|:----:|---------|
| `&2A` | `*` | **Synchronisation** — a full block *header* follows. `&2A` = `%00101010`, alternating ones and zeroes (the tape sync pattern) |
| `&23` | `#` | **Inter-block marker** — a headerless continuation data block follows (a ROMFS shortcut; tape repeats the full header) |
| `&2B` | `+` | **End of filing system** — no more files (a single byte after the last block) |

These three values and their roles are confirmed by the MOS reader: it
syncs on `&2A`, reads a continuation block on `&23`, and resets at `&2B`
when it reaches the end of the ROM's data.

### 2.2 Block header

A header block begins with the `&2A` sync byte, then the following fields
(the fixed fields in order, then the two CRCs):

| Field | Size | Encoding | Notes |
|-------|-----:|----------|-------|
| Sync | 1 | `&2A` | start of header block |
| Name | 1–10 + 1 | ASCII, NUL-terminated | upper-cased; spaces → `_`; truncated to 10 |
| Load address | 4 | little-endian | Acorn load address |
| Exec address | 4 | little-endian | Acorn execution address |
| Block number | 2 | little-endian | 0 for the first block, incrementing |
| Block length | 2 | little-endian | data bytes *in this block*, 0–256 |
| Flag | 1 | bitfield | see below |
| End-of-file address | 4 | little-endian | the **address of the first byte after the end of the file** in paged-ROM space (`&80xx`–`&BFxx`) — i.e. where the *next* file begins. Lets the OS catalogue quickly by skipping over each file's data rather than reading it; `*OPT1,2` forces the slow read-everything path. On *tape* this field is four `&00` bytes; ROMFS reuses it (MOS) |
| Header CRC | 2 | **big-endian** | CRC-16 over the header from the name through the end-of-file address |

Then, if block length > 0:

| Field | Size | Encoding |
|-------|-----:|----------|
| Data | *block length* | raw bytes |
| Data CRC | 2 | **big-endian** CRC-16 over the data |

The header CRC and data CRC are stored most-significant-byte first
(big-endian), unlike the little-endian multi-byte integer fields.

### 2.3 Flag byte

| Bit | Mask | Meaning |
|----:|-----:|---------|
| 7 | `&80` | **Last block** of this file |
| 6 | `&40` | **No data** in this block (block length 0); set by `OPENOUT…:CLOSE#` |
| 5–1 | — | unused |
| 0 | `&01` | **`*RUN`-only** copy protection: the file may be `*RUN` but not `*LOAD`ed / `*EXEC`ed / `CHAIN`ed. The MOS calls it "locked" and raises `"Locked"` on a load (OS 1.20 `checkFileAttributes` → `fileLocked`). It is **read** protection, not the disc filing systems' delete-lock |

bit 0 is its own access axis — surfaced as **`Access.X`** ("run-only"),
*not* `Access.L` (the DFS/ADFS delete-lock). The two never map to each
other: copying a delete-locked DFS file into ROMFS does not `*RUN`-protect
it (which would make its loader unrunnable), and a `*RUN`-only ROMFS file
copied to a disc does not become delete-locked. ROMFS itself has no
delete-lock — the medium is read-only / rebuilt wholesale — so a created
ROM's `disc rm` is never gated by it.

A file of ≤ 256 bytes is a single block whose flag has bit 7 set (it is
simultaneously the first and the last block). A zero-length file is a
single block with flag `&C0` (last + empty).

The MOS reader treats a load address of all four `&FF` bytes specially: it
raises a "Bad address" error, so `&FFFFFFFF` is not a legal load address
for a ROMFS file.

### 2.4 Multi-block files

For a file spanning *N* > 1 blocks, the layout is:

1. **Block 0** — full header (sync `&2A`), flag *without* `&80`, 256 data
   bytes, data CRC.
2. **Middle blocks** (`1 … N-2`) — a single `&23` inter-block marker
   (no header), 256 data bytes, data CRC.
3. **Last block** (`N-1`) — full header (sync `&2A`), flag *with* `&80`,
   the final 1–256 data bytes, data CRC.

So the full header is repeated on the *last* block as well as the
first; middle blocks are headerless. The header must reappear on the last
block because a `&23` continuation block carries no flag byte, so the
final block re-syncs with `&2A` precisely to deliver the `&80` "last
block" flag. A `&23` continuation block has no length field either, so it
is implicitly a full **256-byte** block; only the first and last blocks
state an explicit block length. The reader is therefore a small state
machine: at each boundary, `&2A` → parse a header (its flag bit 7 ends the
file), `&23` → read a 256-byte continuation block, `&2B` → end of filing
system.

> Generators differ in detail: the MOS reader is happy with `&23` for all
> blocks after the first, so a builder that emits only block-0 headers and
> drives completion purely from block lengths is also valid. The reader
> should tolerate either a header (`&2A`) or an inter-block marker (`&23`)
> at each boundary and not assume the last block re-syncs.

> **Files whose length is an exact multiple of 256.** The sideways-ROM
> notes say a final block with bit 6 (no data) may be appended so the
> end-of-file flag has somewhere to live. The Acorn corpus does **not** do
> this: `STRCOM1` (8192 bytes) and `STRCOM2` (9216 bytes) end on a full
> 256-byte block with bit 7 set and no trailing empty block, and both
> round-trip byte-exact. This package's serialiser follows the corpus (no
> trailing empty block); the round-trip test guards the assumption, and a
> future image built the other way would surface as a round-trip failure
> to be handled then. The *parser* copes with either form regardless.

### 2.5 The title block

The first object in the chain is conventionally a **zero-length file**
naming the filing system — its catalogue/title marker, and the title `*.`
displays. **Detection is positional: a zero-length *first* file.** The name
style varies by author:

- **Acornsoft cartridges** wrap it in asterisks: `*Hopper01*`, `*Snap00*`,
  `*Doom01*`, `*Star01*`, `*Star02*` (the asterisks are part of the stored
  name). The New Advanced User Guide example likewise writes `*<title>*`.
- **The BBC Master Demonstration cartridges** use a **bare** name —
  `DEMO-A`, `DEMO-B` — matching the paged-ROM header title, with no
  asterisks. So a parser must **not** key off asterisks; key off "first
  file, length 0". This package strips surrounding asterisks if present
  and exposes the result as the disc title.
- **Some ROMs have none.** The BBC Zalaga ROM begins directly with the
  real `ZALAGA` file (non-zero length), so it has no title block and no
  `*.` title; its meaningful name is the *header* title `RFS id:298DE`
  (shown by `*HELP`, §2.9), a separate string.

The Acornsoft title block's flag is **`&81` (last + run-only)**, *not* the
`&C0` (last + empty) that the New Advanced User Guide `*EXAMPLE*` example emits:
Acorn leaves the `&40` empty bit clear even on a zero-length block. A
reader must therefore treat "block length 0", not "empty bit set", as the
test for an empty block.

### 2.6 End of filing system

After the last file's last block, a single `&2B` byte marks the end (MOS).
A reader scanning block boundaries stops when it meets `&2B` — or, more
defensively, any byte that is neither a `&2A` sync nor a `&23` inter-block
marker where a block is expected, or when the end-of-file address runs
past the ROM bank.

### 2.7 The OS read state machine

`LoadFromROM.pdf` traces how the MOS reads a file from ROM, driven by a
byte `fsReadProgressState`. The same routine serves tape and ROM through a
unified `readByteFromTapeOrROM`; for ROM the carrier-tone states are
skipped and there is no ACIA wait. The states are:

| State | Meaning |
|------:|---------|
| 0 | done — exit |
| 1 | looking for carrier tone *(tape only)* |
| 2 | found carrier tone, waiting for sync byte `&2A` *(tape only)* |
| 3 | found sync byte `&2A`, now reading header |
| 4 | header read with non-zero block length, now reading block data |
| 5 | finished reading this block's data — set state back to 0 |

For ROM, the loader initialises straight to state 4 once a header has been
read (`setStateForLoadingBlockDataOrReset`), since states 1–3 are the tape
carrier/sync search. The notable routines:

- **`searchForFile` → `searchForBlockReadHeaderAndCompare`** — walk the
  block chain reading each header and comparing the filename.
- **`checkForROMBlockMarker` / `startOfBlock`** — *"checks for the
  synchronisation byte, which is different for the first block; increments
  the block number as needed."* This is the OS confirming that the first
  block of a file carries the `&2A` header while subsequent blocks use the
  `&23` shortcut, and that blocks are numbered sequentially.
- **`loadBlock` → `blockNumbersMatch`** — the assembled file's blocks must
  arrive in order; the loader checks each block number against the
  expected next value.
- **`checkFileAttributes` / `loadOrRun`** — apply the load/exec addresses
  and the flag bits (`*RUN` vs `*LOAD`, run-only).

The practical consequence for the parser: read the first header (`&2A`),
then for each subsequent boundary expect either another header (`&2A`,
re-syncing to deliver a flag — e.g. the last block) or a `&23`
continuation block; track the block number to keep blocks in order; stop
when a header's flag has bit 7 set, or at the `&2B` end marker.

### 2.8 The `*.` catalogue display

`*.` lists the filing system. Each line is, in order:

```
<name>  <last-block-number>  <total-length>  <load>  <exec>
```

- **name** — the file name (the title block prints with its `*…*`).
- **last-block-number** (2 hex digits) — the block number of the file's
  *final* block, i.e. `total_blocks − 1`. It equals the high byte of the
  total length whenever the last block is short (the usual case).
- **total-length** (4 hex digits) — the whole file in bytes:
  `last_block_number × 256 + last_block_length`.
- **load**, **exec** (8 hex digits each) — the Acorn load and execution
  addresses from the file header.

Worked example — `Electron_Hopper.rom`, against a real BBC `*.`:

```
*Hopper01* 00 0000    00000000 00000000      title block, 0 bytes, 1 block
!BOOT      00 003A    00001E86 00001E86      0x3A = 58 bytes, 1 block
HOPPER     03 03D5    00000000 00000000      4 blocks (last = 3), 981 bytes
HOPOBJ     22 2257    00003000 00003000      35 blocks (last = 0x22), 8791 bytes
```

So the two numeric columns are the **last block number** and the **total
length** — not, as one might guess, a block count and a CRC.

### 2.9 `*HELP` versus `*.` — two different "titles"

`*HELP` prints the **paged-ROM header title** (§1.1, at `&8009`) — the
ROM's own name in the sideways-ROM table — while `*.` lists the
**filing-system catalogue** (§2.8). They are independent strings:

- Zalaga: `*HELP` → `RFS id:298DE` (a meaningful header title); `*.` lists
  only `ZALAGA`, with no title block.
- The Acornsoft cartridges: `*HELP` → the generic `ROM Cartridge`; `*.`
  shows the `*…*` title block (`*Hopper01*`, …) as the disc title.

The package surfaces the *filing-system* title (the `*…*` block when
present) via the `Titled` capability, since that is what users see as the
disc/catalogue name. The header title is incidental metadata.

### 2.10 How the OS reads a ROM: the service-call interface

The filing-system data is inert on its own. The OS reads it through the
ROM's **service handler** (the machine code between the header and the
data), driven by MOS service calls. A ROMFS ROM must answer at least:

- **`&0D` — initialise the ROM filing system.** On entry `Y` = `15 − next
  ROM to scan`. If that selects *this* ROM (`15 − Y == &F4`, the current
  ROM socket), the handler points the OS read pointer at the start of the
  filing-system data: `STA &F6` / `STA &F7` (low/high of the data address),
  sets `&F5` = `15 − own ROM number`, and claims the call.
- **`&0E` — return the next byte.** If this is the selected ROM, load the
  byte at `(&F6),Y=0`, increment the `&F6/&F7` pointer (carry into `&F7`),
  and claim. This is the byte-at-a-time spigot the loader in §2.7 pulls.

> **The `&0D` scan number: machine differences the handler must survive.**
> The OS passes the serial-ROM scan number in `Y` (and `&F5`) on the init
> call, and the BBC and Electron seed it *differently*:
>
> - **BBC OS 1.20 / Master** seed `&FF` and `INC` to `&00`, so the first init
>   arrives with `Y = 0` (positive).
> - **Electron OS** seeds `&EF` and `INC`s to `&F0`, so the first init arrives
>   with `Y = &F0` (**negative**). The genuine Acornsoft handlers test this
>   first (`TYA : BMI <select self>`) and claim unconditionally — "initialise
>   from the top RFS ROM". A handler without it never initialises on an Elk.
>
> - **The socket-0 wrap.** At each `&2B` the MOS `INC`s the scan number and
>   re-issues `&0D` to chain into a lower socket; the filing system ends only
>   when no ROM claims. The Guide's example inverts with `EOR #&FF : AND #&0F`,
>   masking the high nibble — so a socket-0 ROM (which sets `&F5 = &0F` on
>   selection) sees
>   `&F5` step `&0F → &10` and the mask fold it back to `15 ≥ 0`, re-claiming
>   itself and looping `*CAT` forever. The genuine ROMs invert with `EOR #&0F`
>   (high nibble intact) and test `CMP #&10 : BCS exit`, so the hunt
>   terminates. **Note:** the wrap guard must come *after* the negative-`Y`
>   test and operate on the *inverted* value — testing the raw scan number
>   (`&F0 ≥ &10`) would reject the Electron's init.
>
> This package's created handler does both, matching the genuine ROMs (the
> extra bytes move the empty-header anchor from `&805D` to `&8063`). Sockets
> 1–15 on the BBC are unaffected either way.

A richer handler may also answer:

- **`&09` — `*HELP`.** Print the ROM name and version; optionally compare
  the text after `*HELP` (via the pointer at `&F2/&F3` plus `Y`, forced
  upper-case with `AND #&DF`) against a keyword to print extended help.
- **`&04` — unrecognised `*` command.** If no ROM claims a command the OS
  passes it to the filing system, which may `*RUN` it from the library.

Note what is *absent*: **`&03` (auto-boot)** is for a *filing-system* ROM —
DFS, ADFS, NFS — to select itself on `Shift-Break` and run a `!BOOT`. A
ROMFS data ROM does not answer it; the ROM Filing System lives in the MOS,
not in the ROM (see §2.11). The `!BOOT` files in the corpus are run by the
MOS's RFS or a loader, not by the data ROM itself.

**Consequence for the write path.** *Reading and identifying* a ROMFS image
needs none of this — the bytes are self-describing. But **creating** one
does: a freshly serialised filing system is unreadable by a real machine
until a `&0D`/`&0E` handler is prepended. This is exactly the opaque
preamble this package preserves (§1.2) and refuses to mutate (the
plain-versus-composite split in `docs/architecture.md`). `disc create
--filesystem romfs` therefore emits such a handler (`oaknut.romfs.handler`):
the bare `&0D`/`&0E` handler is the canonical New Advanced User Guide one,
with the `&0D` path following the genuine Acornsoft ROMs where the Guide's
example is wrong — selecting self on a negative scan number (so it
initialises on the Electron) and guarding the scan number against wrapping
(so it works in socket 0): 87 bytes, data at `&8063` for an empty header;
see §2.10. By default a `&09` `*HELP` responder is added that
prints the ROM's title — so the created ROM answers `*HELP` with its
title. The handler is assembled by a small two-pass 6502 assembler so its
branch and jump targets are correct by construction, and a created ROM has
been confirmed in a 6502 emulator (`*HELP`, `*CAT`, `CHAIN` and `*TYPE` all
work).

### 2.11 ROMFS is data, not a filing system — and what "booting" means

A crucial distinction, easy to blur. The **ROM Filing System is part of the
MOS** — it is the filing system selected by `*ROM`, sitting alongside the
tape filing system (both live in MOS chapter 18). A paged ROM "for ROMFS"
does **not** implement a filing system. It only implements the byte-serving
protocol of §2.10 — answer `&0D` by pointing the OS at its data, answer
`&0E` with the next byte (plus, optionally, `&09` for `*HELP`). The MOS's
RFS is what interprets those bytes as a catalogue of files. The ROM is the
*medium*; the filing system is the *driver*, and the driver is in the OS.

This reframes "booting":

- **Filing-system boot** — `Shift-Break` → service call `&03` → an FS ROM
  finds and runs `!BOOT` — is the business of a *filing-system* ROM (the
  DFS ROM, the ADFS ROM, …) or of the MOS's own RFS. A ROMFS *data* ROM has
  no filing system to boot; for it to hunt for `!BOOT` would be to
  re-implement the RFS that already lives in the MOS. So a created data ROM
  does not, and should not, answer `&03`.
- **Cartridge autostart** — a cartridge that *runs on power-on/reset*, as
  the Acornsoft Electron titles do, achieves that by being a **language
  ROM**: ROM type bit 6 set (their `&C2`), with a real `JMP language` entry
  that the MOS enters at reset. The game's own code then loads its data
  through the RFS. That autostart is a property of the ROM being a
  *language*, entirely orthogonal to ROMFS-as-a-filing-system — it just
  happens that such cartridges *also* carry RFS data for the game to read.

`oaknut` creates **data** ROMs: service-only (`&82`), no language entry, the
minimal `&0D`/`&0E` (+ `&09`) handler. They are neither languages nor
filing-system ROMs, so they neither autostart (no language entry) nor
auto-boot a `!BOOT` (not a data ROM's role). They are driven by hand —
`*ROM`, then `*EXEC !BOOT` / `*RUN` / `CHAIN` — exactly as §2.10's
operations allow. A self-*starting* cartridge would be a different artifact:
a language ROM wrapping a loader, wrapping (optionally) RFS data. It is not
built here — it would be a language-ROM feature that happens to use ROMFS,
rather than "a ROMFS feature" — but it is a sensible, well-precedented
addition (it is how the Acornsoft cartridges work), penciled in as a future
feature in `docs/architecture.md`: a `--autostart` create option that adds
a `JMP language` entry and a small stub which `OSCLI`s `*ROM` then
`*EXEC !BOOT`.

## 3. The CRC algorithm

Both CRCs are the CFS/tape CRC: CRC-16-CCITT, polynomial `0x1021`,
initial value `0x0000`, processed most-significant-bit first, **stored
big-endian**. The New Advanced User Guide computes it as:

```python
def crc16_ccitt(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (((crc ^ 0x0810) << 1) + 1) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
```

The `0x0810`/`+1` formulation is an equivalent rearrangement of the
standard `0x1021` polynomial step. The header CRC covers the header bytes
*after* the sync byte (name through next-file pointer); the data CRC
covers that block's data bytes.

## 4. Worked reference (the New Advanced User Guide example)

The New Advanced User Guide's worked example checks out as:

```perl
crc(pack("Z* L L S S C L", "*EXAMPLE*", 0, 0, 0, 0, 0xC0, 0x809E))
```

i.e. a title block named `*EXAMPLE*`, load = exec = 0, block 0, length 0,
flag `&C0` (last + empty), next-file pointer `&809E`. Reproducing this CRC
is a good first unit test for the CRC implementation, and the whole record
is a good first fixture for the header parser.

## 5. Open questions

Resolved by the MOS reader disassembly and the reference corpus: the
marker bytes and their roles (§2.1), the flag-bit meanings (§2.3), the
end-of-file-address field (§2.2), `&2B` end-of-filesystem detection
(§2.6), the data-start (scan for first CRC-valid `&2A`, §1.2), the
title-block convention (`*…*`-wrapped, §2.5), and the `*.` columns (§2.8).
Still to confirm:

1. ~~**BBC vs. Electron** differences~~ — **resolved**: the BBC Zalaga ROM
   and the Electron cartridges share an identical on-ROM format (§6). Only
   authoring differs (type byte, language entry, presence of a title
   block); the service handler is machine code the parser never executes.
2. **Multi-ROM spanning** — see §7. Mechanism understood from MOS 1.20 and
   the sideways-ROM notes, but **no spanning image is yet in the corpus**
   to verify a reassembler against, so it is unimplemented.
3. ~~**Non-Acornsoft / non-cartridge ROMFS**~~ — **resolved**: a genuine
   tool-built ROM (`Snapper_mkromfs.rom`, service-only `&82`, `&C0`
   empty-flag title block) is now in the corpus. It exercises the `bit 7`
   type test, and the reader preserves the `&C0` "no data" bit so it
   round-trips byte-exact (the writer otherwise re-derives the flag; see
   `ROMFSFile.flag_extra`).

## 6. Reference corpus

Twelve ROM images live at the workspace root under
`tests/data/images/romfs/`, all 16 KiB, all decoding with valid header and
data CRCs: eight Acornsoft Electron cartridges (including the two-disc
Countdown To Doom, Starship Command and Tree Of Knowledge), two BBC Master
Demonstration cartridges (`DEMO-A` / `DEMO-B`), one BBC Micro ROM
(`Zalaga`), and one tool-built image — `Snapper_mkromfs.rom` (service-only
`&82`, a `&C0` empty-flag title
block, and the unguarded handler from §2.10). The on-ROM format is
*identical* across machines (§5); they differ only in *authoring*:

| | Acornsoft cartridges | Zalaga (BBC) |
|---|---|---|
| ROM type | `&C2` (service + language) | `&82` (service only) |
| Language entry | `JMP language` | `00 00 00` (none) |
| Header title | generic `ROM Cartridge` | `RFS id:298DE` |
| Copyright | `(C) 1984 Acornsoft` | `(C)2006 Richard Ford` |
| Title block | present (`*…*`) | **absent** |

These are the parser's primary test vectors — each row is
`name  last-block#  length  load  exec  flags`, exactly as decoded from the
bytes and (for Hopper and Zalaga) confirmed against a real BBC `*.`:

```
Electron_Hopper.rom                 FS data @ &80BB
  *Hopper01*  blk &00  len &000000  load &00000000  exec &00000000  last+lock
  !BOOT       blk &00  len &00003A  load &00001E86  exec &00001E86  last
  HOPPER      blk &03  len &0003D5  load &00000000  exec &00000000  last
  HOPOBJ      blk &22  len &002257  load &00003000  exec &00003000  last+lock

Electron_Snapper.rom                FS data @ &80BB
  *Snap00*    blk &00  len &000000  load &00000000  exec &00000000  last+lock
  !BOOT       blk &00  len &00003B  load &00001E87  exec &00001E87  last
  SNAPPER     blk &04  len &00046A  load &00000000  exec &00000000  last
  SNAPOBJ     blk &28  len &002847  load &00000E00  exec &00003400  last+lock

Electron_Countdown_To_Doom_1.rom    FS data @ &829C
  *Doom01*    blk &00  len &000000  load &00000000  exec &00000000  last+lock
  !BOOT       blk &00  len &000038  load &00001E84  exec &00001E84  last
  DOOM        blk &04  len &000407  load &00000000  exec &00000000  last
  INIT        blk &08  len &0008F8  load &00003BFB  exec &00000000  last

Electron_Countdown_To_Doom_2.rom    FS data @ &80BB  (part 2, plain)
  *Doom02*    blk &00  len &000000  load &00000000  exec &00000000  last+lock
  DOOM2       blk &3C  len &003C08  load &00000000  exec &00000000  last

Electron_Starship_Command_1.rom     FS data @ &80BB
  *Star01*    blk &00  len &000000  load &00000000  exec &00000000  last+lock
  !BOOT       blk &00  len &000038  load &00001E84  exec &00001E84  last
  STAR        blk &04  len &000402  load &00000000  exec &00000000  last
  STRCOM1     blk &1F  len &002000  load &00000E00  exec &000047B1  last+lock

Electron_Starship_Command_2.rom     FS data @ &80BB
  *Star02*    blk &00  len &000000  load &00000000  exec &00000000  last+lock
  STRCOM2     blk &23  len &002400  load &00002E00  exec &000047B1  last

Electron_Tree_Of_Knowledge_1.rom    FS data @ &80BB
  *Tree01*    blk &00  len &000000  load &00000000  exec &00000000  last+lock
  !BOOT       blk &00  len &000039  load &00001E85  exec &00001E85  last
  KNOWL       blk &04  len &000406  load &00000000  exec &00000000  last
  TREE        blk &2F  len &002FC1  load &00000000  exec &00000000  last
  M/C         blk &05  len &0005BB  load &00005240  exec &00005240  last

Electron_Tree_Of_Knowledge_2.rom    FS data @ &80BB
  *Tree02*    blk &00  len &000000  load &00000000  exec &00000000  last+lock
  CLASS       blk &09  len &000941  load &00004A51  exec &00000000  last
  FRUIT       blk &05  len &00057B  load &00004A51  exec &00000000  last
```

`Tree Of Knowledge 1` carries a file named **`M/C`** — a `/` in a
filename. ROMFS / CFS names are flat byte strings terminated by NUL, so
`/` is an ordinary name character, **not** a path separator. The flat
mount addresses it as the whole name; nothing splits on `/`.

Countdown To Doom is a **two-disc** game: part 1 (`*Doom01*` — a
`!BOOT`/`DOOM`/`INIT` bootstrap whose real game code is in the 12 KiB
composite tail after the `+`, §1.2) and part 2 (`*Doom02*` — the single
large `DOOM2` file, a plain ROM with `&FF` padding). The two are
**independent** cartridges with different catalogues, *not* a spanning
pair. Starship Command, Tree Of Knowledge and the Master Demonstration are
likewise two independent cartridges each. So **every** `_1`/`_2` pair in
the corpus is independent, none a *spanning* set — each member is a
self-contained ROMFS with its own `+` (see §7).

```
Zalaga.rom  (BBC Micro)             FS data @ &810B, no title block
  ZALAGA      blk &2D  len &002D25  load &00003000  exec &00004522  last+lock
```

Zalaga is the parser's robustness fixture: a service-only (`&82`) ROM with
no title block, a single 46-block file, and a **differing load/exec**
(`&3000` / `&4522`) — confirmed against a real BBC `*.` showing
`ZALAGA  2D 2D25  00003000 00004522`.

## 7. Multi-ROM (slot-spanning) filing systems

A filing system larger than one 16 KiB ROM can be carried by several ROMs
fitted in adjacent sideways sockets; the OS presents them as one
catalogue. The mechanism below was pinned down from the MOS catalogue/read
loop while diagnosing the socket-0 handler bug (§2.10), and corroborated
by *New Advanced User Guide* §17.5.

> **Status.** The mechanism is well-established (it is the exact code path
> that makes a lone socket-0 ROM loop `*CAT`). **No verified slot-spanning
> image is yet in the corpus**, so the creating/reading/writing guidance in
> §7.4 is a design grounded in that mechanism, to be confirmed on real
> hardware before it is built.

### 7.1 How the OS chains ROMs

The OS reads a byte stream served by the active ROM's `&0E` handler, and
*selects* which ROM serves it with `&0D`:

- **Selection (`&0D`).** The OS scans sideways sockets high→low. A ROM with
  RFS data claims the call, records itself as the active RFS ROM in `&F5`,
  and points the read pointer `&F6/&F7` at *its own* data start (past its
  header and handler). The highest-priority RFS ROM is selected first.
- **Reading (`&0E`).** Returns the next byte and advances `&F6/&F7`.
  Crucially, **the standard handler never signals "end of ROM"** — it just
  keeps returning bytes (and, past the data, `&FF` padding). So the only
  thing that ends a ROM's contribution to the stream is a `&2B` *in the
  data*.
- **Hand-off at `&2B`.** When the read loop reads a `&2B` it does
  `INC &F5` and re-issues `&0D` to find the **next-lower** claiming RFS
  ROM. If one claims, reading continues from *its* data start; if none
  does, the filing system ends. This is exactly the loop that makes a lone
  socket-0 ROM re-claim itself and loop `*CAT` forever (§2.10).

So the logical filing system is the **concatenation of whole, self-
contained member ROMs**, read top-socket→bottom, ending at the `&2B` of
the lowest member.

### 7.2 The hard constraint: no file crosses a ROM boundary

Because each member self-terminates with its **own `&2B`** (the NAUG calls
it the "end of ROM marker", per ROM), and the OS only hands off *at* a
`&2B`:

- **Every file lives wholly within one member ROM.** A file's CFS block
  chain cannot straddle a join — there is no mechanism to resume a
  half-read file in the next ROM. (This corrects an earlier guess that a
  chain could "straddle the chip boundary"; it cannot.)
- **Each member is an independently valid ROMFS**: its own paged-ROM
  header, its own `&0D`/`&0E` handler, its own block chain, its own `&2B`,
  padded to its bank size. Fitted on its own, a member still catalogues and
  reads correctly.
- **Members are ordered by socket priority, highest first.** The OS reads
  the highest-socket member first, so the `!BOOT` / loader belongs in that
  member; lower members hold continuation files only.
- **Each member keeps its own title block**, so the combined catalogue
  shows them all (e.g. `*Doom01*` then `*Doom02*`); by convention the
  title's trailing digits are the part number.
- **The socket-0 caveat applies to whichever member is lowest.** With the
  unguarded New Advanced User Guide handler a member in socket 0 loops `*CAT`;
  oaknut's handler carries the `CMP #&10` guard (§2.10), so its members are
  safe in any socket.

The corpus pairs show this *shape* without being one volume: Countdown To
Doom 1/2, Starship Command 1/2 and Tree Of Knowledge 1/2 each carry
`!BOOT` + loader + early files in part 1 and continuation data with no
`!BOOT` in part 2. But they are distributed as separate discs/cartridges
(§6), not a co-resident set — complementary contents are consistent with
slot-spanning but are not proof of it.

### 7.3 A set cannot be detected from content

A well-formed member is a complete, standalone ROMFS — it has its own
`&2B`, header and handler, so there is **no byte signal** that it is "part
2 of a set". Therefore:

- **Grouping must be explicit**, never inferred. Either an ordered source
  (top socket first, e.g. `first.rom second.rom`) or a sidecar manifest
  listing members in socket order. Never join by an `_1`/`_2` filename
  suffix — every such pair in the corpus is independent, so that would
  fabricate a set.
- The **incomplete-ROM handling** below is for genuinely **truncated or
  damaged** images, *not* for recognising set members — a normal member is
  complete and indistinguishable from a standalone ROM.

### 7.4 Creating, reading and writing sets in `oaknut-romfs` (design)

The single-image plug-in contract stays: one `ImageReader` = one member
ROM = one `Mount`. A *set* is a thin native layer above that, never a
single `Mount` straddling several images.

**Reading.** A native aggregate — `ROMFS.from_roms([top, …, bottom])` (or a
`ROMFSSet`) — parses each member with `ROMFS.from_bytes` and concatenates
their file lists in socket order, which is exactly what the OS catalogue
shows. The flat CFS namespace is *not* de-duplicated across members, so the
set is the simple concatenation, member title blocks included. A single
member still reads standalone.

**Creating.** Given a file list and a per-member capacity (8 or 16 KiB):
- Pack **whole** files into members in order — a bin-packing problem, each
  member sized to fit its files plus header + handler + `&2B`. A file too
  large for one member **cannot be stored at all**: it cannot be split, so
  fail with a clear error rather than silently truncating.
- Emit each member as a self-contained ROMFS (the existing
  `build_rom_image` path): the `!BOOT` / loader in the first
  (highest-socket) member, each member terminated by `&2B`, each carrying
  the guarded handler.
- Give each member a title block following the part-number convention
  (`*Name01*`, `*Name02*`, …).

**Writing.** Members are independent and each ≤ 16 KiB, so rewrite only the
affected member wholesale (the existing write path):
- A file lives in exactly one member; editing it rewrites that member only.
- Adding a file places it in a member with room; if none has room, add a
  member (or fail, if the socket/capacity budget is fixed).
- No cross-member rebalancing is needed for correctness, though a
  `compact`-style repack could even out free space across members.

### 7.5 Implemented today (single-ROM safety net)

- **Graceful read-only handling of an incomplete ROM.** `ROMFS.from_bytes`
  does not fail on a ROM with no `&2B`; it parses the complete files
  (dropping any dangling trailing file) and sets `is_complete = False`.
  Such an image still identifies as `acorn-romfs` (demoted to `PROBABLE`,
  evidence noting "incomplete"), is readable for its complete files, and is
  **read-only** at the mount. One ROM alone cannot tell a genuine fragment
  from a truncated image, so both are handled the same safe way. Multi-ROM
  *reassembly* (§7.4) still waits for a verified example.
- **Incompleteness in `disc stat`.** A `StatusReporting` capability on the
  `oaknut.filesystem` axis carries short status notes; the ROMFS mount
  returns "incomplete — … (read-only)" for a fragment and "composite — …
  (read-only)" for a composite ROM, and `disc stat`'s `_partition_block`
  feature-detects it and renders a Notes row — no ROMFS-specific code in
  `oaknut-disc`.

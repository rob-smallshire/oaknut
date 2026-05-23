# RetroClinic Data Centre `cfbackup` `.dat` images

This note is a working analysis of the disc-image format produced by
the **RetroClinic Data Centre** Compact Flash backup utility
(`cfbackup.exe`) and consumed by its sibling restore utility
(`cfrestore.exe`). Both ship on the Data Centre install CD and are
designed to round-trip an 8-bit ADFS filesystem between a CF card
mounted in a USB reader and a Windows host.

The images are read by:

* **ADFS Explorer** (`g7jjf.com/adfs_explorer.htm`) — closed-source.
* **Disc Image Manager** (`github.com/geraldholdsworth/DiscImageManager`).
* **BeebEm** for Windows (`Src/Ide.cpp`) when the Data Centre patched
  ADFS ROMs (`ADFS133.bin`, `ADFS153.bin`) are loaded.

We have four sample images under
`tests/data/images/data-centre/`:

| File | File size (bytes) | FSM total size | First free sector |
|------|------------------:|---------------:|------------------:|
| `cf_b131.dat`     | 4,308,480 | 520,028,160 | 16,830 |
| `cf1gb_v102.dat`  | 2,693,120 | 520,028,160 | 10,520 |
| `cf1gb_v103.dat`  | 2,535,936 | 520,028,160 |  9,906 |
| `cf1gb_t107.dat`  | 3,083,008 | 507,052,032 | 12,043 |

The naming convention (per the bundled `ReadMe.txt`) is `<host>_<rom>.dat`:
prefix `b` = BBC Model B with disc system, `v` = Master 128, `t` = BBC
Model B with no disc interface.

## Headline result

The `.dat` file is a **plain linear stream of 256-byte ADFS sectors**:
ADFS sector *N* lives at file offset *N* × 256. There is **no
interleaving, no per-sector header, no per-cylinder padding, and no
file-level header**. The on-disc data is exactly an "ADFS Old Map" hard
disc image as documented for Acorn ADFS.

The file is **truncated** at `first_free_sector × 256` — i.e. cfbackup
writes only the prefix of the disc up to (but not including) the first
free sector reported by the free-space map. The four sample images all
honour the invariant `len(file_bytes) == fsm_first_free_sector × 256`
exactly. The tail of the disc, which the FSM reports as one large free
extent reaching to `fsm.total_sectors`, is omitted.

## Evidence

### 1. Old-map checksums validate at the natural offsets

Sectors 0 and 1 of every `.dat` file decode as a perfectly ordinary
ADFS Old Free-Space Map without any offset, byte-swap or de-interleave
transformation. The checksum over bytes `0xFE..0x00` (with carry) at
file offsets `0x000` and `0x100` matches the byte stored at `0xFF` and
`0x1FF` respectively in all four samples — see
`oaknut.adfs.free_space_map._calculate_old_map_checksum` for the
algorithm. (`docs/analysis/data-centre/dc_inspect.py` reports the
status.)

### 2. Root directory `Hugo` signatures sit at the standard ADFS old offsets

The 5-sector (1280-byte) old-format root directory begins at sector 2,
i.e. file offset `0x200`. All four images carry the leading `Hugo`
signature at `0x201..0x204` and the trailing `Hugo` signature at
`0x4FB..0x4FE` — exactly where the ADFS specification places them for
old-format directories.

### 3. The directory tree decodes byte-for-byte against the screenshots

Walking the root with `oaknut.adfs.ADFS.from_buffer`, treating the
buffer as a flat hard disc, reproduces the listings shown by ADFS
Explorer and Disc Image Manager — file names, load/exec addresses,
sizes and sector counts all agree. For `cf_b131.dat` the deep tree under
`$.E.Elite.Program.SRC_*` matches the multi-level expansion in the ADFS
Explorer screenshot down to individual file names.

### 4. BeebEm models the Data Centre IDE interface as 256-byte sectors

BeebEm's `IDEReset/IDERead/IDEWrite` (Src/Ide.cpp) implements the
on-card behaviour the Data Centre ROMs expect:

```c
IDEData = IDERegs[2] * 256;                 // SEC_CT * 256 bytes
long pos = (Track * IDEnumHeads * IDEnumSectors
            + Head * IDEnumSectors + Sector) * 256L;
```

The drive is initialised by the ADFS ROM with `INITIALIZE DEVICE
PARAMETERS` (command `0x91`), `IDEnumSectors = IDERegs[3] = 64`,
`IDEnumHeads = (IDERegs[6] & 0x0F) + 1 = 4`. The translation from CHS
back to LBA is therefore the canonical
`LBA = (C × H × S) + (h × S) + (s − 1)`, with **256 bytes per sector**.

The same ADFS sector address therefore maps 1:1 onto a BeebEm IDE
sector: BeebEm reads/writes `ide<N>.dat` directly with this scheme, and
`cf_<x>.dat` files drop in unchanged. (We've verified this end-to-end:
`oaknut.adfs.ADFS.from_buffer` opens the cfbackup files and reads the
catalogues without any preprocessing.)

### 5. The Data Centre patched IDE driver reads 256 bytes per sector

`ADFS-multi-target/src/IDE_DriverBGET.asm` (the byte-get path) issues
one IDE READ command (opcode `0x08` mapped to IDE `0x20`) and then
loops exactly 256 times reading `IDE_DATA`:

```
ldy    #$00
LACCD: lda    IDE_DATA       ; Get byte from hard drive
       sta    ($BE),Y        ; Store to buffer
       iny
       bne    LACCD          ; Loop for 256 bytes
       jsr    CommandDone    ; Release, get result
```

`SetGeometry` (in `IDE_Driver.asm`) confirms the same numbers BeebEm
emulates:

```
SetGeometry:
        jsr    IDE_WaitforReq
        lda    #64            ; 64 sectors per track
        sta    IDE_SEC_CT
        sta    IDE_SEC_NO
        ldy    #6
        lda    ($B0),Y        ; drive
        lsr    A
        lsr    A
        ora    #3             ; head=3 → 4 heads per cylinder
        jsr    IDE_SetDriveHeadA
        lda    #$91           ; INITIALIZE DEVICE PARAMETERS
        bne    IDE_SetCmd
```

`SetSector` then maps the 21-bit ADFS sector number directly into the
IDE CHS registers, so each ADFS sector address corresponds to one IDE
LBA, and one IDE LBA carries 256 bytes — matching the file layout.

The Data Centre build of this driver tree is selected by
`ADFS-multi-target/src/configs/bbcIDE_hog_DC.inc`, which sets the
`IDE_DC` symbol used to gate the small DC-specific code paths inside
the shared driver source.

### 6. The "Interleaved" label in DIM/ADFS Explorer is a UI default

DiscImageManager's interleave logic
(`DiscImage_ADFS.pas:OffsetToOldDiscAddr`) is gated on
`FFormat = diAcornADFS<<4+$02` (ADFS L floppy) or
`GetMajorFormatNumber = diAcornFS` (Acorn File Server). For ADFS hard
discs (`diAcornADFS<<4+$0F`) the function falls through with
`Result := offset` — i.e. no transform. The "Interleave Type:
Interleaved" line that appears in the *Disc Image Details* dialog for
`cf_b131.dat` is the *default* UI label DIM applies to all ADFS
images (`Finterleave := 2 // Auto, so pick INT for ADFS`); for hard
disc images that label has no effect on byte addressing.

In other words, "interleaved" here is an attribute the tools report
about the *configured logical mapping*, not a transformation the bytes
in `.dat` actually carry.

## File layout, formally

```
file_offset(adfs_sector_N) = N * 256        (0 ≤ N < first_free_sector)
file_size = first_free_sector * 256
```

Sector 0 and sector 1 carry the standard ADFS Old Free Space Map (start
addresses and lengths respectively, with checksum, FreeEnd pointer, disc
identifier, boot option, and disc-size fields). Sector 2 carries the
first sector of the root directory (`Hugo`/`Hugo` framed, 47 entries
of 26 bytes each + tail). All ADFS Old-Map invariants apply unchanged;
no Data Centre-specific extension is present in any of the four sample
images.

The "real" disc capacity reported by the FSM (`OldSize` at offset
`0xFC..0xFE` of sector 0, little-endian, in 256-byte sectors) matches
the formatted capacity of the underlying CF card after a small reserved
area:

* `2,031,360` sectors × 256 = **520,028,160 bytes** (~496 MiB) — three
  of the four cards.
* `1,980,672` sectors × 256 = **507,052,032 bytes** — `cf1gb_t107.dat`.

The 21-bit ADFS sector address space tops out at 2²¹ = 2,097,152
sectors (= 512 MiB). Both observed sizes sit just under that ceiling,
so the geometry is not a Data Centre extension to ADFS — these are
plain ADFS Old-Map discs sized to fit a 512 MiB CF card, with the
backup file truncated to the used prefix.

## Partitioning

The `cfbackup` ReadMe documents an optional final argument:

> if you have a 2GB card with 2 partitions, put a 1 at the end to
> specify partition 1.

Static analysis of `cfbackup.exe` and `cfrestore.exe` (Microsoft VC++
6.0, COFF i386, both built 6 Feb 2009) settles the partition question.
Both tools use the same arithmetic in two places:

1. After opening `\\.\<drive>:`, they multiply the partition argument
   by 2³⁰ and pass it to `SetFilePointer(handle, partition << 30, NULL,
   FILE_BEGIN)` — i.e. partition 1 starts at exactly **byte offset
   1 GiB** on the physical CF card. (cfbackup: `4010f5: shl eax, 0x1e`;
   cfrestore mirrors at the same offset.)

2. Inside the per-sector loop they recompute the byte position as
   `((partition << 21) + sector_no) << 9` — equivalent to
   `partition × 2,097,152 sectors × 512 bytes`, again 1 GiB. (cfbackup:
   `401306: shl ecx, 0x15; ... 40130d: shl ecx, 0x9`. cfrestore:
   `40133e: shl edx, 0x15; ... 401346: shl edx, 0x9`.)

So **partition N starts at LBA `N × 2,097,152`** on the CF card, and a
2 GiB card hosts up to two ADFS partitions of 1 GiB each. The argument
is validated to be 0 or 1 (`cmp eax, 0x1; jg`), so only two partitions
are supported by these utilities.

### CF physical sector size vs. ADFS sector size

The disassembly also confirms the 256-vs-512 puzzle implied by the IDE
ROM driver. Inside the per-sector loop both tools:

* seek to `(partition × 2,097,152 + sector_no) × 512` bytes — i.e. the
  CF card is addressed in 512-byte sectors (the standard physical
  unit), and
* read or write **only 256 bytes** at that position (`push 0x100;
  push buf; call ReadFile/WriteFile-wrapper`).

Each ADFS sector therefore lives in the **first half** of the
corresponding 512-byte CF sector; the second half is unused on the CF
card and absent from the `.dat` file. This matches the patched ADFS
ROM:

* `IDE_DriverBGET.asm` reads exactly 256 bytes per IDE READ (`ldy #0;
  loop: lda IDE_DATA; sta ($BE),Y; iny; bne loop`);
* the main path's `Twice` loop in `IDE_Driver.asm` ends up overwriting
  the first 256 bytes of the IDE buffer with the same first 256 bytes
  in the second pass, leaving only the first 256 bytes effectively
  used.

So the BBC writes/reads only the first 256 bytes of each 512-byte CF
sector, the Windows tools mirror that on the host, and the `.dat` file
is the dense 256-bytes-per-sector concatenation that falls out
naturally.

### What the reverse-engineered backup loop actually does

The relevant slice of `cfbackup.exe` (annotated):

```
; --- Read the 512-byte ADFS Old FSM into a stack buffer ---
401102: lea  eax, [esp+0x180]
401109: push 0x200
40110e: push eax
40110f: call ReadFile-wrapper        ; pulls bytes 0..0x1FF from CF

; --- Parse OldSize at 0xFC..0xFE (24-bit LE) into ebp ---
401133: mov  ebp, [esp+0x27e]        ; byte 0xFE
40113a: mov  ecx, [esp+0x27d]        ; byte 0xFD
401141: mov  edx, [esp+0x27c]        ; byte 0xFC
        ... ebp = (FE<<16)|(FD<<8)|FC

; --- Parse FreeEnd / 3 = number of free entries ---
40115f: mov  ecx, [esp+0x37e]        ; byte 0x1FE (FreeEnd)
        imul by 0x55555556 to divide by 3

; --- Loop: read 3-byte free starts at 0x000+3i and lengths at 0x100+3i ---
        ... build free list, accumulate total free in ebx

; --- Print Size / Free / Used ---
40121f: push ebp; printf "Size : %08X, %d sectors", ebp
401231: push ebx; printf "Free : %08X, %d sectors", ebx
40123d: push (ebp-ebx); printf "Used : %08X, %d sectors", ebp-ebx

; --- For each used run between consecutive free entries: ---
4012a3: printf "Reading %d sectors starting at %d"
4012d0: mov  esi, 0x40                ; batch = min(remaining, 64)
        ; inner per-sector loop:
4012fc: mov  ecx, [esp+0x28]          ; partition
401306: shl  ecx, 0x15                ; ×2,097,152 sectors
401309: add  ecx, edi                 ; +current_sector
40130d: shl  ecx, 0x9                 ; ×512 bytes
401312: push ecx; push handle
401314: call SetFilePointer           ; seek on raw CF
40132a: push 0x100; push buf
401330: call ReadFile-wrapper         ; read 256 bytes
401343: push handle; push 1; push 0x100; push buf
401349: call fwrite-wrapper           ; append 256 bytes to .dat
        ; advance to next sector / next batch / next entry
```

`cfrestore.exe` is the structural mirror (same arithmetic, fread of
256 bytes from the `.dat`, then SetFilePointer + WriteFile to push
those 256 bytes into the first half of the corresponding 512-byte CF
sector).

### Implications for fragmented discs

The outer loop walks the free-space-map entries and, for each gap of
*used* sectors, appends those bytes to the output file with no padding.
On a disc where free space is *not* contiguous at the tail (e.g. after
a lot of churn), `cfbackup` would therefore concatenate disjoint used
runs into a single byte stream — meaning the file would no longer be a
simple linear `sector_n -> offset_n × 256` mapping. None of our four
sample images exhibit this; they all have exactly one free entry, at
the tail of the disc, so the file *is* the linear prefix
`sectors[0:first_free]`.

If `oaknut` ever needs to read or produce backups of fragmented
Data Centre discs, the writer will need to reconstruct the segment
list from the FSM and concatenate the same way; the reader will need
to "blow up" the segments back into a linear sector array using the
free-space entries as guides. (`cfrestore`, by symmetry, is presumably
correct for fragmented inputs because it walks the FSM the same way
on the way back.)

## Round-trip behaviour

Because the `.dat` is truncated, an in-place edit can only succeed when
new data fits in already-allocated sectors (i.e. when overwriting an
existing file or when the catalogue update touches sectors below the
truncation point). To make room for new files the buffer must first be
expanded to `total_sectors × 256` bytes (zero-padded), and then
re-truncated to `first_free_sector × 256` after the change.

A minimal round-trip in Python — verified locally against
`cf_b131.dat`:

```python
src = Path("cf_b131.dat").read_bytes()
total_sectors = src[0xFC] | (src[0xFD]<<8) | (src[0xFE]<<16)
buf = bytearray(src) + bytearray(total_sectors * 256 - len(src))

adfs = ADFS.from_buffer(memoryview(buf))
(adfs.root / "E" / "PROBE").write_bytes(b"hello data centre")

# Re-truncate to the new first-free sector before saving.
new_first_free = buf[0] | (buf[1]<<8) | (buf[2]<<16)
Path("cf_b131_modified.dat").write_bytes(buf[:new_first_free * 256])
```

That suffices for ADFS Explorer / Disc Image Manager / BeebEm to read
the modified image back. The cfrestore tool is expected to behave the
same way provided the card capacity is at least `total_sectors × 256`
bytes (the ReadMe explicitly warns that the destination card must be
the same size or larger).

## Recipe for `oaknut` support

Adding first-class support for cfbackup `.dat` images to `oaknut-adfs`
is straightforward:

1. **Reader.** Already works via `ADFS.from_buffer` on the truncated
   buffer. To allow free-space queries to return correct totals, expose
   a thin `ADFS.from_data_centre_dat(filepath)` constructor that:
   * mmap-opens the file,
   * pads the in-memory view to `fsm.total_sectors × 256` (a `bytearray`
     copy is unavoidable because `mmap` regions can't be silently grown),
   * delegates to `_from_buffer_with_format` with a single-surface
     `SurfaceSpec` covering the full disc.

2. **Writer.** On `close()` (or an explicit `save_data_centre_dat()`),
   re-read `fsm.first_free_sector` from the in-memory buffer and write
   `buffer[: first_free_sector × 256]` back to disk. No `.dsc` sidecar
   is needed — the geometry is implicit (4 heads × 64 sectors × 256
   bytes per cylinder).

3. **Format detection.** A `.dat` whose first 512 bytes parse as a
   valid ADFS Old Map *and* whose `fsm.first_free_sector × 256`
   matches the file size on disk is a Data Centre cfbackup image. The
   conjunction is strong enough to disambiguate from the existing
   `dat`+`dsc` pair format used elsewhere in `oaknut-adfs`.

4. **Geometry sidecar.** Optionally generate a matching `.dsc` on
   export (`heads = 4, sectors_per_track = 64`) so that tooling that
   only understands the SCSI-style geometry pair can also read the
   image. Note that 64 SPT differs from the SCSI default of 33 used
   elsewhere in `oaknut-adfs`; this is an IDE-only geometry.

## Open questions

* **`cfrestore` tail behaviour.** The disassembly shows it writes only
  the chunks the FSM marks as used; the rest of the card is left
  untouched. The "format a card on the beeb first before restoring"
  caveat in the ReadMe is consistent with this — restore does not zero
  the tail, so a freshly partitioned card needs a clean ADFS skeleton
  outside the restored prefix to be readable. This matches the static
  analysis but has not been verified against real hardware.
* **Per-byte verification of round-trip.** The evidence above is
  static (directory listings + binary disassembly). A bit-exact
  empirical round-trip — `cfbackup → oaknut.write → cfrestore →
  cfbackup` and compare — would require the Windows host with a CF
  reader.
* **Fragmented discs.** None of our samples exhibits a non-contiguous
  free-space map. A test image with several small free regions
  scattered through the used portion would let us confirm the
  segment-concatenation behaviour described above.

## Files in this analysis

* `dc_inspect.py` — quick-and-dirty inspector that prints the FSM
  fields, free-space entries, the truncation-invariant check, and a
  root-directory listing for any `.dat` passed on the command line.
  Run with `uv run python docs/analysis/data-centre/dc_inspect.py
  tests/data/images/data-centre/*.dat`.

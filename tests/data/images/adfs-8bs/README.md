# 8BS Archimedes ADFS L discs

Two 640K ADFS L (old map, old directory) Archimedes discs from the 8BS
disc-magazine archive, kept for what RISC OS left in their directories.

## Provenance

Downloaded from the [8BS catalogue](https://8bs.com/catalogue/arc.htm),
Archimedes (ARC) section, on 2026-10-14. The zips hold these images unchanged.

| File | 8BS entry | Source | SHA-256 |
|---|---|---|---|
| `arc-01.640.adf` | ARC-01 "Archimedes 1" | `https://8bs.com/pool/arc/arc-01.zip` | `0127ca1032e431e13c9348426a5885932ae7bea8ca3731f8c32fd5cf93fec4e3` |
| `arc-03.640.adf` | ARC-03 "Archimedes 3" | `https://8bs.com/pool/arc/arc-03.zip` | `77563af19f79b53eea48fbfdcfc18309560b4cca6ae80c90adaf073030962aa1` |

## What they exercise

Both are interleaved despite the `.adf` suffix.

- **Old-directory check bytes (#87).** RISC OS writes the PRM's ROR-13
  checksum into the check byte (&4FF) of an old directory it changes; 8-bit
  ADFS neither checks nor maintains it. The subdirectories carry correct
  RISC OS checksums, while each root carries a stale one: arc-01 stores &9C
  (true &30), arc-03 stores &A2 (true &79).
- **A damaged disc.** 8BS notes that ARC-03 has files missing data. Three of
  its root's subdirectories (`!Warfarin`, `!Xchanger`, `Music`) point at
  sectors filled with &A5, so neither 640K layout reads the whole tree.
  The interleaved layout reads eight directories to the linear layout's two.
- **BASIC V.** arc-01's `!RunImage` programs are RISC OS BASIC V, swept by
  the BASIC corpus test.

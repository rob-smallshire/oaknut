# HFE fixtures

| File | Source | Contents |
|---|---|---|
| `Dunjunz_D1S1_40T_HG3_8518BF40_1.hfe` | Capture of the original 1987 Bug-Byte Dunjunz flippy disc, side 1, by Stardot user Pernod (#93) | HFE v3, 41 tracks, 1 side, FM, 250 kbit/s, 300 rpm. Acorn DFS "MASTER 128 V", 19 files, boot option 3. Tracks 0-39 formatted 10 x 256, 2-sector skew per track; track 40 unformatted. |
| `Dunjunz_D1S2_40T_HG3_54F4B47A_1.hfe` | As above, side 2 | Same header. Acorn DFS "Dunjunz", 31 files, boot option 0; catalogue claims 800 sectors on a 40-track side. |
| `Dunjunz_D1S1_40T_HG3_8518BF40_1.ssd`, `Dunjunz_D1S2_40T_HG3_54F4B47A_1.ssd` | Read from the HFE files through Beebium's emulated 8271 (acornaeology/dunjunz `tools/read_disc_image.py`) | Golden 40-track sector images (102,400 bytes) for HFE flattening. |
| `Citadel_FSD0174_1.hfe` | Beebium test assets | HFE v3, 80 tracks, 1 side, FM. Acorn DFS "SUPERIOR", 7 files on tracks 0-39; tracks 40-79 are entirely weak (RAND) samples. |

The Dunjunz captures follow the naming of the `beeb_hfe` preservation
archive and are its Bug Byte *Dunjunz* entries (variant 1 of each side).
The spreadsheet rows, with links to the archived HFE and SuperCard Pro
captures, are in `packages/oaknut-hfe/docs/references.md`.

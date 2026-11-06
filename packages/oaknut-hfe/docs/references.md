# HFE references

## The `beeb_hfe` archive and its fingerprint spreadsheet

A community preservation archive of HFE flux captures of original BBC
Micro discs, together with the spreadsheet that catalogues and
fingerprints them, with submissions credited to their contributors.
Between them they are the best source of real HFE images for
`oaknut-hfe`, including copy-protected originals.

- **Archive:** [`beeb_hfe`](https://drive.google.com/drive/folders/140xzJarpb3HX04MaqR_m8AzDoG3Bdyky)
  (public Google Drive folder). One folder per publisher (A & B, Abacus
  Software, Acornsoft, Addison Wesley, Alligata, BBC Soft, Beebug,
  Bug-Byte, Computer Concepts, …), around fifty in all, dated April and
  May 2020.
- **Catalogue:** [BBC discs and fingerprints](https://docs.google.com/spreadsheets/d/1q006avySqZMcUGuqPlpFOgKLgdRTOzj9gucy3pS2Uks/edit?gid=0#gid=0)
  (public Google Sheet). One row per captured disc variant, with these
  columns: Publisher, Title, Disc, Tracks, HFE Grab version, CRC32,
  CRC32 as 40 tracks (if 80 track disc), Variant, DFS title, DFS cycle
  number, Birthday (YY/MM/DD), HFE link, Submitter, TRKS or scp files
  link, Duplicates, Notes.

The Notes column records protection schemes and compatibility details
disc by disc. For example, the Acornsoft *Elite* entry notes deleted
128-byte sectors and IDs of &F6 upwards. Those notes are the reference
for what `disc hfe sectors --anomalies` should find on a protected disc.
Some rows also link SuperCard Pro (`.scp`) or `TRKS` captures alongside
the HFE.

### Capture filenames

Captures are named after the spreadsheet's columns:
`<Title>_<Disc>_<Tracks>_<HFE Grab version>_<CRC32>_<Variant>.hfe`. For
example, `Dunjunz_D1S1_40T_HG3_8518BF40_1.hfe` is disc 1, side 1, 40
tracks, grabbed with HFE Grab version 3, fingerprint `8518BF40`,
variant 1.

### The Dunjunz fixtures

The two Dunjunz fixtures in `tests/data/images/hfe/` are the archive's
Bug Byte *Dunjunz* captures. The spreadsheet lists them as follows
(the [CSV export](https://docs.google.com/spreadsheets/d/1q006avySqZMcUGuqPlpFOgKLgdRTOzj9gucy3pS2Uks/export?format=csv&gid=0)
needs no sign-in):

| Disc | DFS title | Cycle | CRC32 | Variant | HFE | SuperCard Pro |
|---|---|---|---|---|---|---|
| D1S1 (boot, Master) | MASTER 128 V | 42 | `8518BF40` | 1 | [HFE](https://drive.google.com/file/d/1rye-LddKf8QQbptq_RygSqA7hGh2mgh8/view) | [scp](https://drive.google.com/file/d/1tyOOQzfVwL3qDnAYdPykxH0DaFdNW5OO/view) |
| D1S2 (model B) | Dunjunz | 59 | `54F4B47A` | 1 | [HFE](https://drive.google.com/file/d/1eIC_chzpCjD2594nZk2JLwPipScQU9TJ/view) | [scp](https://drive.google.com/file/d/1HZ_u0eRBjkUtWCyjsOU-X0jfjlwgbZm5/view) |

Both are 40-track captures made with HFE Grab version 3, submitted by
VectorEyes, with duplicates from VectorEyes, pumpkin and ip, and no
birthday. Only variant 1 is listed. The cycle numbers are written in hex
without a prefix: they match the catalogue cycle bytes &42 and &59. The
Notes are empty for both sides, which agrees with the decode: neither
side is protected.

The fingerprint is not the CRC32 of the `.hfe` file, nor of the sector
image it flattens to (checked on both Dunjunz sides). The spreadsheet
does not say what it is computed over.

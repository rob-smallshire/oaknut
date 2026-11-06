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
variant 1. The two Dunjunz fixtures in `tests/data/images/hfe/` come from this
effort.

The fingerprint is not the CRC32 of the `.hfe` file, nor of the sector
image it flattens to (checked on both Dunjunz sides). The spreadsheet
does not say what it is computed over.

# Truncated ADFS images

## `welcome-master-compact.adm`

The Master Compact Welcome disc ("Welcome 1.03C Iss4"), captured as only the
first half of the disc.

| | |
|---|---|
| Source | SevernWolf's `master compact welcome.zip`, Stardot thread <https://stardot.org.uk/forums/viewtopic.php?t=33348>, attached to issue #88 |
| Size | 327,680 bytes (1280 sectors) |
| MD5 | `fe146ebf7f8fe1ac4c7a325d5e37dfbb` |
| SHA-256 | `23d36498d31dd6a62f765cf69ed14ff86df3d1b88990157ba39bca15f19023e2` |

The free-space map gives the disc size as &A00 (2560) sectors: an 80-track
double-sided L-format disc, imaged in logical-sector order and cut off at
sector 1280. Everything below that reads correctly. The objects the image
cannot hold:

| Object | Start sector | Kind |
|---|---|---|
| `$.WIMPS.P` | 1325 | directory, wholly past the end |
| `$.WIMPS.R` | 1455 | directory, wholly past the end |
| `$.WIMPS.Pad` | 1425 | file, wholly past the end |
| `$.LIBRARY.view` | 1642 | file, wholly past the end |
| `$.WIMPS.Index1` | 1261 | file, 64 sectors, runs past the end |

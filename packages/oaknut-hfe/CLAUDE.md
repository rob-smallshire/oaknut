# CLAUDE.md — oaknut-hfe

Package-specific guidance; the workspace-root `CLAUDE.md` has the
cross-cutting rules. Read that first.

## Scope

Read-only HFE (HxC Floppy Emulator) flux images, v1 (`HXCPICFE`) and v3
(`HXCHFEV3`). Writing HFE exists (`write_hfe`) for building test images;
nothing writes changes back into a capture.

## Pipeline (one module per stage)

| Module | Stage |
|---|---|
| `container.py` | Header, track table, 256-byte side interleave, bit reversal, v3 opcodes → `TrackSamples` (a `"0"`/`"1"` sample string per side) |
| `ibm.py` | FM/MFM half-cell codec, address-mark patterns, CRC-16/CCITT |
| `decode.py` | Samples → `DecodedSector`s: every ID mark at any bit offset, both densities, every sampling phase merged |
| `flat.py` | Decoded disc → logical sector image (`FlatImage`), layout inferred from the sectors, not the header |
| `report.py` | Remarks on each track/sector's departures from the layout (the protection report) |
| `build.py` | Sectors → half-cells → samples, with deliberate defects, for tests |
| `decoder.py` | `HFEDecoder` on the `oaknut.decoder` axis, so `reader_for` (and every `disc` command) opens `.hfe` transparently |
| `cli.py` | `disc hfe info / sectors / flatten` |

The module is `flat`, not `flatten`: the package exports a `flatten()`
function, which would shadow a same-named module.

## Facts that are easy to get wrong

- Samples are on a clock of twice the header bit rate (2 µs at 250 kbit/s):
  an FM half-cell is **two** samples, an MFM half-cell one.
- v3 opcodes are recognised **after** bit reversal (raw `0x8F` is SETINDEX).
- SKIPBITS discards the first *n* samples of the byte after its count byte.
  Beebium kept them instead; nothing in its fixtures exercises it.
- RAND (weak) bytes read as zero samples, and are counted.
- The header's encoding field is the capture tool's expectation; decode
  searches every track for FM and MFM regardless.
- FM size codes honour three bits (8271, up to 16 KiB); MFM two (WD1770).

## Provenance

Ported from Beebium (`~/Code/beebium`: `HfeFormatHandler`, `IbmDiscFormat`,
`TrackBuilder`), which is the user's own code, relicensed MIT here. Beebium's
`TrackDecoder` assumes word-aligned marks and is deliberately not followed.

## Sources of real captures

`docs/references.md` records the `beeb_hfe` archive of HFE captures of
original BBC discs and the "BBC discs and fingerprints" spreadsheet that
catalogues them, including per-disc copy-protection notes and the
capture filename convention. Look there first for a real protected
fixture.

## Testing

Fixtures in `tests/data/images/hfe/` (see its README): two sides of the
Dunjunz capture from #93 with golden SSDs read through Beebium's emulated
8271 (flattening must match them byte for byte), and Beebium's Citadel
capture (80-track HFE of a 40-track disc, RAND-filled tail). Protection
tricks are tested on tracks made with `build.py`, not on real captures.
CLI tests live in `packages/oaknut-disc/tests/test_cli_hfe.py`.

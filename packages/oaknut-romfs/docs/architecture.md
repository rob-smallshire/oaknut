# oaknut-romfs architecture

This package follows the established oaknut two-layer pattern: a
self-contained **native API** that models the ROMFS on-ROM format and
knows nothing about the plug-in system, plus a thin **Extension adapter**
that exposes that API on the `oaknut.filesystem` axis so the `disc` CLI and
the identification coordinator can use it. See the workspace `CLAUDE.md`
layering table and `docs/romfs-format-spec.md` for the byte layout.

## Layering within the package

```
filesystem.py    AcornROMFS(Filesystem) + _ROMFSMount   ← plug-in adapter
      │                 probe() / open() / geometry_grammar()
      ▼
romfs.py         ROMFS                                   ← native API
      │                 title, version, copyright, iter files, read file
      ▼
block.py         ROMFSBlock + block-chain parse          ← CFS block codec
      │                 header fields, flag bits, CRC verify
      ▼
crc.py           crc16_ccitt()                           ← CFS/tape CRC
      ▼
ImageReader (oaknut.filesystem.reader)                   ← clamped ROM bytes
```

Dependencies flow strictly downward, mirroring oaknut-dfs.

## Native API (planned modules)

- **`crc.py`** — `crc16_ccitt(data) -> int`, the CFS CRC (poly `0x1021`,
  big-endian on disc). The smallest, most testable unit; its first test is
  the NAUG `*EXAMPLE*` worked example from the format spec.
- **`block.py`** — `ROMFSBlock`: parse/serialise one CFS block (sync,
  name, load, exec, block number, length, flag, next-file pointer, header
  CRC, data, data CRC) and the flag-bit helpers (`last`, `empty`,
  `locked`). Tolerant of both header (`&2A`) and inter-block (`&23`)
  boundaries.
- **`romfs.py`** — `ROMFS`, the user-facing class. Parses the paged-ROM
  header (title, binary version, version string, copyright) and the block
  chain into a flat list of files; exposes title and per-file access
  (name, load/exec, length, lock, contents). A `ROMFSFile` /
  `ROMFSStat` pair mirrors the DFS `DFSPath` / `DFSStat` ergonomics.
- **`exceptions.py`** — `ROMFSError` base (a `FSError` from
  `oaknut.file`), with `NotAROMFSError`, `CRCError`,
  `TruncatedROMError`, etc.

## Extension adapter (`filesystem.py`)

`AcornROMFS(Filesystem)` adapts the native API to the plug-in contract:

- **`probe(reader)`** — structural identification. Strong signals: the
  ROM type byte at `&8006` has **bit 7 set** (service entry — the corpus
  cartridges are `&C2`, mkromfs is `&82`, so test the bit, not the value);
  a copyright string beginning `(C)` at the offset named by `&8007`; and a
  well-formed first block found by **scanning for the first `&2A` whose
  header CRC validates** (the data start varies with handler size). With
  CRC agreement this reaches `Confidence.STRONG`. The evidence tuple is
  the single source of truth, as in the DFS unification (`match_evidence()`
  → derive `matches()`). Note the displayed disc title comes from the
  `*…*` title block, not the generic header title (`"ROM Cartridge"`).
- **`open(reader, geometry, surface=0)`** — wrap a `ROMFS` over
  `reader.buffer()` and return `_ROMFSMount`.
- **`geometry_grammar()`** — ROMFS has no disc geometry; the grammar
  models the ROM as a single linear surface sized to the image (an 8 KiB
  or 16 KiB bank). No floppy/winchester kinds.

### Capabilities the mount provides

| Capability | Provided? | Why |
|---|:--:|---|
| `Mount` (core) | yes | flat list + read; `path_root()` is `""` |
| `AcornMetadata` | yes | CFS load/exec + lock bit |
| `Titled` | yes | the ROM title string |
| `HierarchicalDirectories` | **no** | ROMFS is flat — no directories |
| `Bootable` | **no** | no `*OPT 4` boot byte on ROM |
| `FreeSpace` / `Sized` | maybe | ROM is fixed; free space is the unused tail to the `&2B` marker / bank end |
| `Validatable` | yes (later) | header + per-block CRC verification |
| `RegionHost` | **no** | ROMFS reserves nothing |
| `UserDatabase`, `Compactable`, `FreeMap`, `PhysicalGeometry` | **no** | not applicable to ROM |

Writing (`write_bytes`, `create`) is deferred. The medium is read-only
ROM; identification and reading come first. If image creation is added
(equivalent to `mkromfs`) it is reached only via `--filesystem romfs`, so
`creates` stays empty and ROMFS is never inferred as a default creator
from a file extension.

## Identification and registration

When the adapter is ready, registration is two entry points in
`pyproject.toml` (currently commented out there, pending the first passing
probe against a real image):

```toml
[project.entry-points."oaknut.filesystem"]
acorn-romfs = "oaknut.romfs.filesystem:AcornROMFS"

[project.entry-points."oaknut.command"]   # optional, [cli] extra
romfs = "oaknut.romfs.cli:romfs"
```

The coordinator discovers ROMFS purely via the entry point; no change to
`oaknut-disc` or `oaknut-filesystem` is needed.

## Build order (test-first)

1. `crc.py` + test against the NAUG `*EXAMPLE*` CRC.
2. `block.py` + tests parsing the `*EXAMPLE*` header record and a small
   single-block file, verifying header/data CRCs.
3. `romfs.py` + tests: parse a real reference ROM's header (title,
   version, copyright) and enumerate its files.
4. `filesystem.py` `probe()` + test: a reference ROM identifies as
   `acorn-romfs` with the expected evidence; a non-ROMFS blob does not.
5. `_ROMFSMount` read path + tests (`iter_entries`, `read_bytes`,
   `acorn_meta`, `title`).
6. Wire the entry point; add a `disc identify` / `disc ls` integration
   test over a reference image.
7. (Optional, later) creation/serialisation round-trip.

## Test data

Reference ROMFS images live at the workspace root under
`tests/data/images/romfs/`, reached via
`tests.fixtures.REFERENCE_IMAGES_DIRPATH`. They are committed to git, not
synthesised, so the parser is validated against genuine Acorn output.

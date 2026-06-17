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
| `Mount` (core) | yes | flat list + read + write; `path_root()` is `""` |
| `AcornMetadata` | yes | CFS load/exec + lock bit |
| `Titled` | yes | the ROM title string |
| `StatusReporting` | yes | flags an incomplete (fragment) or composite ROM as read-only in `disc stat` |
| `HierarchicalDirectories` | **no** | ROMFS is flat — no directories |
| `Bootable` | **no** | no `*OPT 4` boot byte on ROM |
| `FreeSpace` / `Sized` | maybe | ROM is fixed; free space is the unused tail to the `&2B` marker / bank end |
| `Validatable` | yes (later) | header + per-block CRC verification |
| `RegionHost` | **no** | ROMFS reserves nothing |
| `UserDatabase`, `Compactable`, `FreeMap`, `PhysicalGeometry` | **no** | not applicable to ROM |

### Creation

`disc create foo.rom` (or `--filesystem acorn-romfs`) builds a fresh image
via `build_rom_image`: a service-only (`&82`) paged-ROM header, a service
handler, a `*title*` title block, the `&2B` marker, and `&FF` padding. Only
the two real sizes are offered — **16 KiB** (default) and **8 KiB** (`--geometry
8k`). `creates = {".rom"}`, so `.rom` infers ROMFS.

The handler is assembled by a small two-pass 6502 assembler
(`handler.py`) so branch/jump targets are correct by construction. The bare
`&0D`/`&0E` handler is based on the canonical mkromfs/NAUG one but follows
the genuine Acornsoft ROMs in the `&0D` path — 87 bytes, putting data at
`&8063` for an empty header (the test anchor). It treats a negative scan
number as "select self" (the Electron's MOS issues the init with `Y`
negative, so without this a created ROM never initialises on an Elk) and
guards the scan number against wrapping past the sixteen sockets (otherwise
a socket-0 ROM re-claims itself at the `&2B` and loops `*CAT` forever). By
default a `&09` `*HELP` responder is also included, printing the title (so
the title is the `*HELP` message). A created ROM has been confirmed in a
6502 emulator: `*HELP` prints the title, and `*CAT` / `CHAIN` / `*TYPE`
read files correctly.

Writing (`write_bytes`, `create`) is deferred. The medium is read-only
ROM; identification and reading come first. If image creation is added
(equivalent to `mkromfs`) it is reached only via `--filesystem romfs`, so
`creates` stays empty and ROMFS is never inferred as a default creator
from a file extension.

## Identification and registration

Registration is the entry point in `pyproject.toml`:

```toml
[project.entry-points."oaknut.filesystem"]
acorn-romfs = "oaknut.romfs.filesystem:AcornROMFS"
```

The coordinator discovers ROMFS purely via the entry point; no change to
`oaknut-disc` or `oaknut-filesystem` is needed. A `disc romfs` command
group on the `oaknut.command` axis (behind the `[cli]` extra) can be added
later.

## Write contract: plain versus composite ROMs

A ROMFS image is one of two shapes:

- **Plain ROMFS** — everything after the `&2B` end marker is padding to the
  end of the ROM (Hopper, Snapper, Starship Command). Fully read/write.
- **Composite ROM** — opaque content follows the filing system: a service
  handler answering `*HELP` (service call `&09`) and friends, or a
  co-resident language (Countdown To Doom). `ROMFS.to_bytes()` preserves
  that content verbatim at its original address, and the **mount treats a
  composite ROM as read-only** (`ReadOnlyFilesystemError`), because the
  trailing code may hold absolute pointers into the filing-system region
  that a re-layout would invalidate. Reading, `identify`, `ls` and copy-out
  always work; only mutation is refused. `ROMFS.is_plain` makes the
  distinction.

The filing system may grow only into the padding run immediately after the
original `&2B`; exceeding it raises `ROMFullError` rather than overwriting
anything.

## Build order (test-first) — status

1. ✅ `crc.py` — CRC-16/XMODEM, verified against the NAUG `*EXAMPLE*` and a
   real Hopper header CRC.
2. ✅ `block.py` — `BlockHeader` parse/serialise + flag bits, round-trip.
3. ✅ `romfs.py` read path — header + chain → files, all CRCs verified,
   against the whole corpus.
4. ✅ `romfs.py` write path — `to_bytes` byte-exact round-trip over all
   seven images; `with_files` for mutation; `ROMFullError`.
5. ✅ `filesystem.py` — `probe()`, `open()`, geometry; the `_ROMFSMount`
   read core plus `AcornMetadata` and `Titled`; the write surface gated on
   `is_plain`.
6. ✅ Entry point wired; `disc identify` / `disc ls` confirmed end-to-end.
7. ✅ **Creation** (`disc create foo.rom`): a service-only `&82` header, the
   `&0D`/`&0E` handler plus a `&09` `*HELP` responder printing the title,
   a `*title*` block, and padding; 8/16 KiB; `creates = {".rom"}`. The
   handler runs in a 6502 emulator. `StatusReporting` flags read-only ROMs
   in `disc stat`.
8. ✅ `disc romfs` admin subcommands (`oaknut.command` axis): get-/set-
   copyright and get-/set-version, querying and mutating an existing
   image's header (set-copyright rebuilds on a length change, for a
   created-style ROM only).
9. ⬜ BBC BASIC detokenisation for files stored as tokenised BASIC
   (mirroring the DFS package), once a use-case needs it.
10. ⬜ Multi-ROM **spanning** reassembler — deferred until a genuine
    spanning example exists (§7 of the format spec).
11. ⬜ **Self-starting (language-ROM) cartridges** — see below.

## Future: self-starting cartridges (the language-ROM technique)

A created ROM is a *data* ROM (`&82`): the player must `*ROM` then
`*EXEC !BOOT` by hand (§2.11 of the format spec). The Acornsoft Electron
cartridges instead *start themselves* on power-on or `Shift-Break` by being
**language ROMs** — and we can emit the same.

Sketch (`disc create --autostart`, or a `disc romfs make-bootable`
transform):

- Set ROM type bit 6 → **`&C2`** (service **+ language** + 6502), and write
  a real `JMP language` at `&8000` instead of the null `00 00 00`.
- Emit a short **language stub** beside the `&0D`/`&0E` handler. On entry
  the MOS has printed the title; the stub flattens the stack
  (`LDX #&FF : TXS`), re-enables interrupts (`CLI`), then issues the boot
  via `OSCLI` (`&FFF7`) — e.g. `*ROM` then `*EXEC !BOOT` — so the game's own
  loader takes over. The boot command would default to `*EXEC !BOOT` (the
  DFS boot-option-3 equivalent) and be overridable.
- The stub is hand-assembled by the existing two-pass assembler
  (`handler.py`); it needs `OSCLI` and an embedded command string. As with
  the service handler, assemble for correctness then confirm execution in a
  6502 emulator.

Why it's a clean fit: it reuses the assembler and the create/rebuild path,
and it is exactly the documented mechanism (§2.11) — a language ROM that
*also* carries ROMFS data. Caveats: it produces a `&C2` ROM (so it would be
read-only to our writer afterwards, by the language-entry rule in
`set_copyright`), and the language-ROM contract has real subtleties (the
error vector, never returning), so the stub needs care and emulator
testing. Sensible, but a distinct artifact from the plain data cartridge —
hence penciled in rather than built.

## Test data

Reference ROMFS images live at the workspace root under
`tests/data/images/romfs/`, reached via
`tests.fixtures.REFERENCE_IMAGES_DIRPATH`. They are committed to git, not
synthesised, so the parser is validated against genuine Acorn output.

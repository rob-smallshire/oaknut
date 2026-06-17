# CLAUDE.md — oaknut-romfs

This file provides guidance to Claude Code when working specifically in
`packages/oaknut-romfs/`. The top-level `CLAUDE.md` at the workspace root
has the cross-cutting rules (PEP 420 namespace guard, commit style,
variable naming suffixes, British "disc" spelling, test-first
preference). Read that first; this file only adds what is specific to the
ROMFS package.

## Scope

`oaknut-romfs` hosts the Acorn ROM Filing System: the filing system used
by paged ROMs (sideways ROMs and cartridges) on the BBC Micro and Acorn
Electron. The backing store is a **linear paged-ROM image**, not a
sectored disc, and files are stored in **Cassette Filing System (CFS)
block format** — so ROMFS is the closest sibling of the cassette filing
system, not of the disc filing systems.

Consequences that shape the whole package:

- **Flat namespace.** ROMFS has no directories. The mount will *not*
  advertise `HierarchicalDirectories`.
- **CFS metadata.** Files carry an Acorn load address, execution address
  and a lock bit (`AcornMetadata`); the ROM carries a title (`Titled`).
- **Read-mostly.** The medium is ROM. Reading and identification come
  first; image *creation* is a later, optional concern
  and only via `--filesystem`, never as a default creator (`creates`
  stays empty).
- **Byte-linear geometry.** There is no meaningful disc geometry — a
  ROMFS image is a flat byte range (typically an 8 KiB or 16 KiB bank).
  The geometry grammar models the ROM as a single linear surface; it is
  not a floppy or a winchester.

See `docs/romfs-format-spec.md` for the authoritative on-ROM byte layout
(derived from the New Advanced User Guide and J.G. Harston's MakeRFS)
and `docs/architecture.md` for the planned module layout and how the
native API maps onto the `oaknut.filesystem` plug-in contract.

## Layer flow (planned)

The package follows the established two-layer pattern: a self-contained
native API that knows nothing of the plug-in system, plus a thin adapter
in `filesystem.py` that exposes it on the `oaknut.filesystem` axis.

```
AcornROMFS (filesystem.py)        ← oaknut.filesystem.Filesystem adapter
  ↓  probe() / open()
ROMFS (romfs.py)                  ← native API: header + file chain
  ↓
ROMFSBlock / block chain          ← CFS-format block parse/serialise
  ↓
ImageReader (oaknut.filesystem)   ← clamped linear view of the ROM bytes
```

It depends on:

- `oaknut-file` — `AcornMeta`, `Access`, `FSError`, the `'acorn'` text
  codec.
- `oaknut-filesystem` — the `Filesystem`/`Mount` contract, `ImageReader`,
  `Identification`, `Geometry`.
- `oaknut-discimage` — `SurfaceSpec`/`Geometry` building blocks for the
  trivial linear ROM geometry.
- `oaknut-basic` — BBC BASIC detokenisation for files stored as
  tokenised BASIC, mirroring the DFS package.

## Testing

Reference ROMFS images live at the workspace root under
`tests/data/images/romfs/` (reached via `tests.fixtures
.REFERENCE_IMAGES_DIRPATH`), not inside this package — commit them to git
rather than skipping tests when absent. Build format tests test-first
against those real Electron/BBC ROM images.

```sh
uv run pytest packages/oaknut-romfs/tests -q
```

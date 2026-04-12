# CLAUDE.md — oaknut-afs

This file provides guidance to Claude Code when working specifically in
`packages/oaknut-afs/`. The top-level `CLAUDE.md` at the workspace root
has the cross-cutting rules (PEP 420 namespace guard, commit style,
variable naming suffixes, British "disc" spelling, etc.) — read that
first; this file only adds what is specific to the AFS package.

## Scope

`oaknut-afs` implements the Acorn Level 3 File Server on-disc format,
identified by the `AFS0` magic. It is **not** the Econet client
protocol (NFS / ANFS); it is the server's private disc layout. AFS
lives in the tail cylinders of an old-map ADFS hard-disc image,
coexisting with the ADFS partition on the same physical image.

Depends on:

- `oaknut-file` — for `FSError`, `BootOption`, `host_bridge`, `Access`
  (the standard Acorn attribute byte used on the wire by
  PiEconetBridge); AFS has its own on-disc access byte whose layout
  differs, implemented in `oaknut.afs.access.AFSAccess`.
- `oaknut-discimage` — for `SectorsView`, `UnifiedDisc`, `Surface`,
  `SurfaceSpec`.
- `oaknut-adfs` — the AFS region is addressed through an ADFS disc.
  Repartitioning mutates `OldFreeSpaceMap`, and compaction before
  repartitioning uses the existing `ADFS.compact()` method.

## Primary sources

Three external sources, in decreasing order of authority:

1. **L3V126 ROM source** at `/Users/rjs/Code/L3V126/` — the actual
   Level 3 File Server. When sources disagree, the ROM wins.
2. **Beebmaster's PDF**, "Understanding the Acorn Level 3 File Server
   Structure", at
   `/Users/rjs/Code/beebium/scripts/wfsinit/Understanding the Acorn Level 3 File Server Structure.pdf`.
3. **WFSINIT.bas** at `/Users/rjs/Code/beebium/scripts/wfsinit/`, with
   a reverse-engineered write-up in `wfsinit.md`.

`docs/afs-onwire.md` at the workspace root is the living specification
that this package's code implements. Every non-obvious fact it records
is cited to `Uade0x.asm:<label>`. When you extract new facts from the
ROM, add them to `afs-onwire.md` and commit before (or with) the code
that depends on them.

## Architecture

See `docs/afs-implementation-plan.md` §2–3 for the module layout. In
brief, modules are layered:

```
cli.py (oaknut-afs-disc entry point)
  ↓
wfsinit/ (partition.py, layout.py, driver.py)
  ↓
AFS (afs.py)  ←  ADFS.afs_partition (oaknut-adfs)
  ↓
AFSPath (path.py)  +  PasswordsFile (passwords.py)
  ↓
merge (merge.py)  +  host_import (host_import.py)  +  libraries/ (LibraryImage)
  ↓
AfsDirectory (directory.py — read + insert/delete/rename/grow)
  ↓
MapSector / MapChain / ExtentStream (map_sector.py)  +  Allocator (allocator.py)
  ↓
CylinderBitmap / BitmapShadow (bitmap.py)
  ↓
InfoSector (info_sector.py)
  ↓
SectorsView (oaknut.discimage.sectors_view)
```

Dependencies flow strictly downward. Info sector, bitmap, and map
sector are the three foundational format layers; directory and
passwords build on them; the AFS class and path wrap the whole stack.
The `wfsinit/` sub-package orchestrates partitioning and initialisation.
`merge.py` and `host_import.py` compose the lower layers for bulk copy.

## Testing

- `uv run pytest packages/oaknut-afs/tests -q` — currently 487+ tests.
- Every format structure gets hand-crafted byte fixtures before it
  acquires any logic. Round-trip tests (parse → serialise, compare
  bytes) are the cheapest bug-finders.
- Golden fixtures transcribed from Beebmaster's PDF live in
  `tests/helpers/beebmaster.py`.
- `tests/helpers/afs_image.py` synthesises complete in-memory AFS
  regions inside `ADFS.create(ADFS_L)` for integration tests without
  needing a captured disc image.
- End-to-end round-trip stability tests in
  `test_round_trip_stability.py` initialise → mutate → reopen → verify.

## Naming conventions

`_filename`, `_filepath`, `_dirpath`, `_dirname` throughout, per
workspace convention. Prose uses British "disc", never "disk".

## PEP 420 discipline

**No `src/oaknut/__init__.py`** — this package contributes to the
shared `oaknut` namespace package. The workspace-level
`scripts/check_no_namespace_init.sh` pre-commit hook enforces this.

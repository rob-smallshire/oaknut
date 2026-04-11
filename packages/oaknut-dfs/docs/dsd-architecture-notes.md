# DSD Architecture Notes

**STATUS: IMPLEMENTED** ✅

This document describes the design and implementation of DSD (double-sided disk) support with independent catalogs per side.

## ~~Current Issue~~ RESOLVED

The current oaknut-dfs implementation treats DSD (double-sided) disk images as a single unified disk with 800 sectors. However, this is **architecturally incorrect** for how BBC Micro DFS actually works.

## How DFS Actually Handles Double-Sided Disks

DFS treats double-sided disks as **two completely separate drives**, not one unified disk:

- **Side 0** (BBC DFS `*DRIVE 0`): First side, sectors 0-399
- **Side 1** (BBC DFS `*DRIVE 2`): Second side, sectors 0-399
- Each side has its **own independent catalog** (sectors 0-1 per side)
- Files on different sides are in completely separate catalogs
- You cannot directly access files on the other side without switching drives

### BBC DFS Drive Numbering (for reference)

The BBC Micro uses these drive numbers:
- `*DRIVE 0` = First physical drive, side 0
- `*DRIVE 1` = Second physical drive, side 0
- `*DRIVE 2` = First physical drive, side 1
- `*DRIVE 3` = Second physical drive, side 1

**Note:** oaknut-dfs uses simple `side` numbers (0, 1) rather than DFS drive numbers to avoid confusion. Each disk image has side 0, and optionally side 1 if double-sided.

## Physical vs. Logical Layout

### Physical Layout (Track Interleaving)
The DSD file format uses track interleaving at the byte level:
- Track 0, side 0 (10 sectors, 2560 bytes)
- Track 0, side 1 (10 sectors, 2560 bytes)
- Track 1, side 0 (10 sectors, 2560 bytes)
- Track 1, side 1 (10 sectors, 2560 bytes)
- ...

The `InterleavedDSDSectorImage` class correctly handles this physical layout.

### Logical Access
From the filesystem's perspective:
- Side 0: Logical sectors 0-399 (catalog at sectors 0-1)
- Side 1: Logical sectors 0-399 (catalog at sectors 0-1)

Each side is accessed independently. In BBC DFS, you switch sides using `*DRIVE n`. In oaknut-dfs, you specify the side when opening the disk.

## Current Implementation

### What Works
- `InterleavedDSDSectorImage` correctly maps logical sectors to physical byte offsets
- Physical track interleaving is handled correctly

### What Needs Fixing
- `DFSImage.open()` for DSD files should expose **both sides separately**
- Each side needs its own `Catalog` instance
- API needs to support drive selection (which side to access)

## Proposed Changes (CHOSEN DESIGN)

### API Design: Separate Open Calls Per Side

The `side` parameter is added to `DFSImage.open()`:

```python
# Open side 0 - works for both SSD and DSD
disk_side0 = DFSImage.open("disk.dsd", side=0)
print(disk_side0.files)  # Files on side 0

# Open side 1 - only works for DSD
disk_side1 = DFSImage.open("disk.dsd", side=1)
print(disk_side1.files)  # Files on side 1

# Default is side=0 for backward compatibility
disk = DFSImage.open("disk.ssd")  # Implicitly side=0

# SSD only has side 0
disk = DFSImage.open("disk.ssd", side=1)  # Raises InvalidFormatError
```

**Validation:**
- SSD files: Only `side=0` is valid, `side=1` raises `InvalidFormatError`
- DSD files: Both `side=0` and `side=1` are valid
- Invalid values (e.g., `side=2`) raise `ValueError`
- Default: `side=0` (for backward compatibility)

**Type Safety:**
The `side` parameter type is `int` with runtime validation. While we could use `Literal[0, 1]` or create a `Side` enum, plain `int` with validation is simpler and more Pythonic for this use case.

## Implementation Summary

The implementation will involve:

1. **Add `side` parameter to `DFSImage.open()`**
   - Type: `int` with default value `0`
   - Validation: Must be 0 or 1
   - SSD images reject `side=1`

2. **Create `DSDSideSectorImage` wrapper class**
   - Wraps `InterleavedDSDSectorImage`
   - Maps logical sectors 0-399 to the correct physical sectors
   - Used by `DFSImage.open()` when opening DSD with specific side

3. **Update `DFSImage._create_sector_image()`**
   - Accept `side` parameter
   - For DSD: Create `InterleavedDSDSectorImage`, then wrap in `DSDSideSectorImage`
   - For SSD: Validate `side=0`, then create `SSDSectorImage`

4. **Add `--side` option to CLI commands**
   - Default to 0 for backward compatibility
   - Update all relevant commands

5. **Update tests and documentation**
   - Test both sides independently
   - Validate that sides cannot see each other's files
   - Update all documentation with side parameter

## Implementation Notes

### Catalog Layer
- No changes needed - `AcornDFSCatalog` already operates on sectors 0-1
- Just need to pass the correct sector image (for the appropriate side)

### Sector Image Layer
Need new sector images that map logical sectors for one side. These wrap `InterleavedDSDSectorImage` and provide a view of a single side:

```python
class DSDSideSectorImage(SectorImage):
    """Access one side of a DSD disk (400 sectors per side).

    Maps logical sector numbers (0-399) to the appropriate physical
    sectors on the selected side of the disk.

    Args:
        underlying: The InterleavedDSDSectorImage to wrap
        side: Which side to access (0 or 1)
    """

    def __init__(self, underlying: InterleavedDSDSectorImage, side: int):
        if side not in (0, 1):
            raise ValueError(f"Invalid side: {side} (must be 0 or 1)")
        self._underlying = underlying
        self._side = side
        self._sectors_per_track = 10
        self._num_tracks = underlying._num_tracks

    def read_sector(self, sector_num: int) -> bytes:
        """Read a logical sector from this side."""
        if not 0 <= sector_num < 400:
            raise ValueError(f"Invalid sector: {sector_num}")
        # Map to physical sector number in interleaved layout
        track = sector_num // self._sectors_per_track
        sector_in_track = sector_num % self._sectors_per_track
        physical = (track * 2 + self._side) * self._sectors_per_track + sector_in_track
        return self._underlying.read_sector(physical)

    def write_sector(self, sector_num: int, data: bytes) -> None:
        """Write a logical sector to this side."""
        # Similar mapping logic for writes
        ...
```

Alternatively, `InterleavedDSDSectorImage` could be modified to accept an optional `side` parameter that restricts it to one side's logical addressing.

### CLI Impact
The CLI will need to support side selection via a `--side` option:
```bash
oaknut-dfs cat disk.dsd --side=0     # Side 0 (default)
oaknut-dfs cat disk.dsd --side=1     # Side 1
oaknut-dfs cat disk.dsd              # Defaults to side 0

# Commands that list contents should indicate which side
oaknut-dfs info disk.dsd --side=0    # Show info for side 0
oaknut-dfs info disk.dsd --side=1    # Show info for side 1
```

**Special handling for some commands:**
- `info` without `--side`: Could show info for both sides
- `cat` without explicit side: Defaults to side 0
- Commands that modify disks: Must specify which side to operate on

## Testing Impact

The `04-double-sided.bas` generator creates:
- Side 0: 13 files (small/medium files in $, files in directory A)
- Side 1: 9 files (large files in $, files in directory B)

Tests will need to validate:
- Both sides can be accessed independently via `side=0` and `side=1`
- Files on one side are not visible from the other
- Each side has correct catalog
- Opening SSD with `side=1` raises `InvalidFormatError`

## References

- BBC Micro Advanced User Guide (DFS section)
- Test generator: `tests/data/generators/04-double-sided.bas`
- Physical interleaving: `src/oaknut_dfs/sector_image.py:InterleavedDSDSectorImage`

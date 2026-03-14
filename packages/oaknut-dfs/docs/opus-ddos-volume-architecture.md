# Opus DDOS Volume Architecture: Analysis and Recommendations

## Executive Summary

Opus DDOS used a partitioned volume system where each physical disk side contained up to 8 independent volumes (A-H), rather than unifying both sides into a single logical space. This document analyzes how Opus DDOS actually worked and recommends implementing volume support at the **Catalogue layer** rather than presenting volumes as additional surfaces.

**Recommendation:** Add optional volume awareness to the `Catalogue` and `DFS` classes, with volumes defaulting to 'A' for compatibility with standard Acorn DFS.

## How Opus DDOS Actually Worked

### Physical Drive Mapping

BBC Micro hardware presented double-sided drives through a control latch at &FE84:
- **Bit 0:** Drive select (0=unit 0, 1=unit 1)
- **Bit 1:** Side select (0=bottom, 1=top)

A typical BBC Micro with 2 double-sided drives exposed 4 logical drive numbers:
- Drive 0: Physical drive 0, side 0
- Drive 1: Physical drive 0, side 1
- Drive 2: Physical drive 1, side 0
- Drive 3: Physical drive 1, side 1

### Opus DDOS Volume System

**Key Insight:** Volumes were **per-drive**, not unified across sides.

Each drive number (0-3) could contain **independent** volumes A-H:
- Drive 0 (side 0): Volumes 0A, 0B, 0C, 0D, 0E, 0F, 0G, 0H
- Drive 2 (side 1): Volumes 2A, 2B, 2C, 2D, 2E, 2F, 2G, 2H

Both sides maintained **separate allocation tables** and catalogs.

### User-Facing Addressing

Files were addressed using combined drive and volume notation:
- Format: `:DriveVolume.Directory.Filename`
- Example: `:2B.$.MENU` = Drive 2, Volume B, root directory, file MENU

**Default Volume:**
- System defaulted to volume 'A'
- Changeable via `*DRIVE` command
- **Acorn DFS disks accessible only through volume A** (compatibility mode)

This design allowed Opus DDOS to read standard Acorn DFS disks by treating them as volume A.

### Track 0 Layout

Each surface's track 0 contained:
- **Sectors 0-1:** Volume A catalog (DFS-style, 2 sectors)
- **Sectors 2-3:** Volume B catalog
- **Sectors 4-5:** Volume C catalog
- **Sectors 6-7:** Volume D catalog
- **Sectors 8-9:** Volume E catalog
- **Sectors 10-11:** Volume F catalog
- **Sectors 12-13:** Volume G catalog
- **Sectors 14-15:** Volume H catalog
- **Sector 16:** Disc allocation table
- **Sector 17:** Reserved/unused
- **Tracks 1-79:** Data storage

### Allocation Table Detailed Structure

Research from MMB Utils reveals the precise byte layout:

```
Offset   Length   Field
------   ------   -----
0x00     1        Format marker (0x20 = fixed value for DDOS)
0x01     2        Disk size in sectors (little-endian)
                  Standard 80-track: 0x05A0 (1440 sectors)
0x03     1        Sectors per track (0x12 = 18 decimal)
0x04     1        Format indicator (0x50 standard, 0xFF also observed)
0x05     3        Reserved/unused
0x08     2        Volume A starting track (16-bit LE word)
0x0A     2        Volume B starting track (16-bit LE word)
0x0C     2        Volume C starting track (16-bit LE word)
0x0E     2        Volume D starting track (16-bit LE word)
0x10     2        Volume E starting track (16-bit LE word)
0x12     2        Volume F starting track (16-bit LE word)
0x14     2        Volume G starting track (16-bit LE word)
0x16     2        Volume H starting track (16-bit LE word)
0x18     232      Additional allocation data
```

**Critical Discovery:** Volume start tracks are **16-bit little-endian words** (2 bytes each), not single bytes. Earlier documentation incorrectly showed these as single bytes at 0x08-0x0F.

**Typical Volume Configuration (80-track disk):**
- Volume A: Track 1 (bytes 0x08-09 = 0x0001) - 56 tracks = 252KB
- Volume B: Track 57/0x39 (bytes 0x0A-0B = 0x0039) - 23 tracks = 103.5KB
- Volumes C-H: Unallocated (bytes = 0x0000)

**Flexible Geometry Support:**

The 16-bit track values support various disk configurations:
- 35-track disks: Bytes allow track numbers 0-255 per volume
- 40-track disks: Standard configuration
- 80-track disks: Most common (1440 sectors total)

Each volume uses **track-based allocation** (4.5KB per track = 18 sectors × 256 bytes) with a maximum size of 252KB (63 tracks, or 0x3F0 sectors).

## Architectural Analysis

### Option 1: Volumes as Additional Surfaces (NOT RECOMMENDED)

Present each Opus volume as a separate `Surface`:

```python
# 8 volumes per side = 16 surfaces for double-sided disk
disc = DiscImage(buffer, [
    spec_0A, spec_0B, spec_0C, ..., spec_0H,  # Drive 0 volumes
    spec_2A, spec_2B, spec_2C, ..., spec_2H,  # Drive 2 volumes
])

surface_0A = disc.surface(0)   # Volume 0A
surface_0B = disc.surface(1)   # Volume 0B
surface_2A = disc.surface(8)   # Volume 2A
```

**Problems:**

1. **Violates Surface Abstraction**
   - `Surface` should represent physical geometry, not logical partitions
   - 16 surfaces for a 2-sided disk is semantically incorrect

2. **Shared Track 0**
   - Track 0 contains allocation table shared by all volumes on that side
   - Can't model as independent surfaces

3. **Breaks Format Detection**
   - File size calculations assume surfaces = physical sides
   - 368,640 bytes = 80 tracks × 18 sectors × 256 bytes × 2 sides
   - NOT 80 tracks × 18 sectors × 256 bytes × 16 "surfaces"

4. **Doesn't Match Actual Architecture**
   - Opus DDOS presented volumes within drives, not as separate drives
   - BBC Micro had 4 drive numbers (0-3), not 16

### Option 2: Volume Support in Catalogue Layer (RECOMMENDED)

Keep existing 2-surface model, add volume awareness to catalogs:

```python
# Double-sided Opus disc (2 physical surfaces)
disc = DiscImage(buffer, [spec0, spec1])

# Surface 0 has OpusDDOSCatalogue managing volumes A-H
catalog0 = OpusDDOSCatalogue(disc.surface(0))
vol_0A = catalog0.get_volume('A')  # Volume A on surface 0
vol_0B = catalog0.get_volume('B')  # Volume B on surface 0

# Surface 1 has separate OpusDDOSCatalogue with volumes A-H
catalog1 = OpusDDOSCatalogue(disc.surface(1))
vol_2A = catalog1.get_volume('A')  # Volume A on surface 1
```

**Advantages:**

1. **Matches Physical Reality**
   - 1 surface = 1 physical disk side
   - Volumes are logical partitions within a surface

2. **Clean Abstraction Layers**
   - Surface layer: Physical geometry (sectors, tracks)
   - Catalogue layer: Logical organization (files, volumes)
   - Clear separation of concerns

3. **No Breaking Changes**
   - Existing formats (Acorn DFS, Watford) unaffected
   - Surface abstraction remains unchanged
   - Volume support is opt-in via catalogue implementation

4. **Natural Extension**
   - Other formats treat surface as single catalog
   - Opus DDOS treats surface as 8 sub-catalogs
   - Same pattern, different granularity

## Implementation Design

### Catalogue Layer Changes

**Base Class Extension (Optional):**

```python
class Catalogue(ABC):
    """Abstract base class for disk catalogs."""

    # Optional volume support (None for non-partitioned formats)
    @property
    def supports_volumes(self) -> bool:
        """Whether this catalogue type supports volumes."""
        return False

    def get_volume(self, letter: str) -> 'Catalogue':
        """
        Get sub-catalogue for specific volume.

        For non-partitioned formats, raises NotImplementedError.
        For Opus DDOS, returns volume-specific catalogue.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support volumes")
```

**Opus DDOS Implementation:**

```python
class OpusDDOSCatalogue(Catalogue):
    """Opus DDOS catalog managing 8 volumes (A-H) on a single surface."""

    CATALOGUE_NAME = "opus-ddos"
    CATALOG_START_SECTOR = 0
    CATALOG_NUM_SECTORS = 18  # Track 0

    @property
    def supports_volumes(self) -> bool:
        return True

    def __init__(self, surface: Surface):
        super().__init__(surface)
        self._volumes = {}
        self._current_volume = 'A'
        self._load_allocation_table()

    def _load_allocation_table(self):
        """Parse disc allocation table and create volume sub-catalogs."""
        sector16 = self._surface.sector_range(16, 1)

        # Parse allocation table header
        self.format_marker = sector16[0]        # Should be 0x20
        self.disk_size = sector16[1] | (sector16[2] << 8)
        self.sectors_per_track = sector16[3]   # Should be 18 (0x12)
        self.format_indicator = sector16[4]    # Typically 0x50 or 0xFF

        # Parse volume start tracks (16-bit little-endian words)
        for i, letter in enumerate('ABCDEFGH'):
            offset = 0x08 + (i * 2)  # Each volume uses 2 bytes
            start_track = sector16[offset] | (sector16[offset + 1] << 8)
            catalog_sector = i * 2  # Volumes A-H in sectors 0-15

            # Only create volume if start track is non-zero (allocated)
            if start_track > 0:
                self._volumes[letter] = OpusDDOSVolume(
                    surface=self._surface,
                    letter=letter,
                    catalog_sector=catalog_sector,
                    start_track=start_track
                )

    def get_volume(self, letter: str) -> 'OpusDDOSVolume':
        """Get specific volume (A-H)."""
        if letter not in 'ABCDEFGH':
            raise ValueError(f"Invalid volume: {letter}. Must be A-H")
        return self._volumes[letter]

    def set_current_volume(self, letter: str) -> None:
        """Set default volume for operations."""
        if letter not in 'ABCDEFGH':
            raise ValueError(f"Invalid volume: {letter}")
        self._current_volume = letter

    # Delegate catalog operations to current volume
    def list_files(self) -> list[FileEntry]:
        return self._volumes[self._current_volume].list_files()

    def find_file(self, filename: str) -> Optional[FileEntry]:
        # Support volume prefix: "B:$.FILE"
        if ':' in filename:
            volume, path = filename.split(':', 1)
            return self.get_volume(volume).find_file(path)
        return self._volumes[self._current_volume].find_file(filename)

    @property
    def max_files(self) -> int:
        return 248  # 31 files × 8 volumes
```

**Volume Sub-Catalog:**

```python
class OpusDDOSVolume(Catalogue):
    """Single volume within an Opus DDOS disc."""

    def __init__(self, surface: Surface, letter: str,
                 catalog_sector: int, start_track: int):
        super().__init__(surface)
        self._letter = letter
        self._catalog_sector = catalog_sector
        self._start_track = start_track

        # Volume catalog is DFS-style, 2 sectors
        self.CATALOG_START_SECTOR = catalog_sector
        self.CATALOG_NUM_SECTORS = 2
        self.MAX_FILES = 31

    def _logical_to_physical_sector(self, logical_sector: int) -> int:
        """
        Convert volume-relative sector to disc-absolute sector.

        Opus DDOS uses track-based allocation:
        - Logical sector 0 = first data sector in volume
        - Physical track = start_track + (logical_sector // sectors_per_track)
        - Physical sector = track * sectors_per_track + (logical_sector % sectors_per_track)
        """
        track_offset = logical_sector // self._surface.sectors_per_track
        sector_in_track = logical_sector % self._surface.sectors_per_track
        physical_track = self._start_track + track_offset
        physical_sector = physical_track * self._surface.sectors_per_track + sector_in_track
        return physical_sector

    # Standard Catalogue methods work on this volume's 2-sector catalog
    def list_files(self) -> list[FileEntry]:
        """List files in this volume (standard DFS catalog parse)."""
        # Read catalog at self._catalog_sector
        # Parse using standard Acorn DFS format
        ...
```

### High-Level API Changes

**DFS Class Extension:**

```python
class DFS:
    """High-level DFS filesystem operations."""

    def __init__(self, catalogued_surface: CataloguedSurface, volume: str = 'A'):
        """
        Initialize DFS instance.

        Args:
            catalogued_surface: Surface with catalog
            volume: Default volume (A-H) for Opus DDOS, ignored for other formats
        """
        self._catalogued_surface = catalogued_surface
        self._current_volume = volume

        # Set volume if catalog supports it
        if hasattr(catalogued_surface.catalogue, 'set_current_volume'):
            catalogued_surface.catalogue.set_current_volume(volume)

    @classmethod
    def from_buffer(cls, buffer: memoryview, disk_format: DiskFormat,
                    side: int = 0, volume: str = 'A') -> "DFS":
        """
        Create DFS from buffer.

        Args:
            buffer: Disk image buffer
            disk_format: Format specification
            side: Which surface to use (0 or 1 for double-sided)
            volume: Default volume (A-H) for Opus DDOS, 'A' for other formats

        Returns:
            DFS instance

        Examples:
            # Acorn DFS (volume parameter ignored)
            dfs = DFS.from_buffer(buf, ACORN_DFS_80T_SINGLE_SIDED, side=0)

            # Opus DDOS - access volume B on side 0
            dfs = DFS.from_buffer(buf, OPUS_DDOS_80T_SINGLE_SIDED,
                                  side=0, volume='B')
        """
        # ... existing code to create catalogued surface ...

        return cls(catalogued, volume=volume)

    def set_volume(self, letter: str) -> None:
        """
        Change current volume (Opus DDOS only).

        For non-partitioned formats, this is a no-op.

        Args:
            letter: Volume letter (A-H)
        """
        if hasattr(self._catalogued_surface.catalogue, 'set_current_volume'):
            self._catalogued_surface.catalogue.set_current_volume(letter)
            self._current_volume = letter

    @property
    def current_volume(self) -> str | None:
        """Get current volume (Opus DDOS) or None (other formats)."""
        if hasattr(self._catalogued_surface.catalogue, 'supports_volumes'):
            if self._catalogued_surface.catalogue.supports_volumes:
                return self._current_volume
        return None
```

## Usage Examples

### Acorn DFS (No Change in Behavior)

```python
from oaknut_dfs.formats import ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED

# Volume parameter ignored for Acorn DFS
dfs = DFS.from_buffer(buffer, ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
                      side=0, volume='B')  # 'B' ignored

files = dfs.list_files()  # Works as before
```

### Opus DDOS - Basic Usage

```python
from oaknut_dfs.formats import OPUS_DDOS_80T_DOUBLE_SIDED_INTERLEAVED

# Access drive 0, volume A (default)
dfs_0a = DFS.from_buffer(buffer, OPUS_DDOS_80T_DOUBLE_SIDED_INTERLEAVED,
                         side=0)  # Defaults to volume='A'
files = dfs_0a.list_files()

# Access drive 0, volume B
dfs_0b = DFS.from_buffer(buffer, OPUS_DDOS_80T_DOUBLE_SIDED_INTERLEAVED,
                         side=0, volume='B')
files = dfs_0b.list_files()

# Access drive 2, volume C (side 1)
dfs_2c = DFS.from_buffer(buffer, OPUS_DDOS_80T_DOUBLE_SIDED_INTERLEAVED,
                         side=1, volume='C')
files = dfs_2c.list_files()
```

### Opus DDOS - Volume Switching

```python
# Create DFS for side 0, volume A
dfs = DFS.from_buffer(buffer, OPUS_DDOS_80T_DOUBLE_SIDED_INTERLEAVED, side=0)

# Work with volume A
files_a = dfs.list_files()

# Switch to volume B
dfs.set_volume('B')
files_b = dfs.list_files()

# Switch back to volume A
dfs.set_volume('A')
```

### Opus DDOS - Volume Prefix in Filenames

```python
dfs = DFS.from_buffer(buffer, OPUS_DDOS_80T_DOUBLE_SIDED_INTERLEAVED, side=0)

# Explicit volume in filename (overrides current volume)
data = dfs.load('B:$.MENU')      # Load from volume B
dfs.save('C:$.DATA', data)       # Save to volume C

# Implicit (uses current volume)
data = dfs.load('$.MENU')        # Uses current volume (A by default)
```

## Comparison: Current vs. Proposed

### Acorn DFS (No Change)

**Current:**
```
Buffer → DiscImage → 2 Surfaces → 2 AcornDFSCatalogues → 2 DFS instances
```

**Proposed:**
```
Buffer → DiscImage → 2 Surfaces → 2 AcornDFSCatalogues → 2 DFS instances
         (same - volume parameter ignored)
```

### Opus DDOS

**Proposed:**
```
Buffer → DiscImage → 2 Surfaces → 2 OpusDDOSCatalogues
                                   │
                                   ├─ Surface 0: 8 volumes (A-H)
                                   │   └─ DFS(side=0, volume='A'...'H')
                                   │
                                   └─ Surface 1: 8 volumes (A-H)
                                       └─ DFS(side=1, volume='A'...'H')

Total: 2 physical sides × 8 volumes = 16 logical "drives"
```

## Design Rationale

### Why Keep Surfaces = Physical Sides

1. **Semantic Correctness**
   - Surface abstraction represents physical disk geometry
   - Mixing logical volumes into physical layer violates abstraction

2. **Format Detection**
   - File size reveals physical geometry, not logical partitions
   - 368,640 bytes = 2 sides × 80 tracks × 18 sectors × 256 bytes

3. **Catalog Independence**
   - Each surface has independent track 0 with allocation table
   - Volumes share allocation table within a surface

4. **Future Extensibility**
   - Other partitioned formats may emerge
   - Cleaner to handle at catalog layer

### Why Add Volume Support to Catalogue

1. **Logical Organization**
   - Volumes are a catalog-level concept (file organization)
   - Not a geometry concept (sector layout)

2. **Format-Specific**
   - Only Opus DDOS uses volumes
   - Other formats can ignore volume API

3. **Backward Compatibility**
   - Volume defaulting to 'A' maintains Acorn DFS compatibility
   - Non-volume formats work unchanged

4. **Natural Delegation**
   - `OpusDDOSCatalogue` delegates to `OpusDDOSVolume` sub-catalogs
   - Each volume is standard DFS-style catalog

## Open Questions

### 1. Volume Navigation

**Question:** Support in-place volume switching or require new DFS instances?

**Option A: In-Place Switching**
```python
dfs = DFS.from_buffer(buffer, format, side=0, volume='A')
dfs.set_volume('B')  # Switch to volume B
```

**Option B: New Instances**
```python
dfs_a = DFS.from_buffer(buffer, format, side=0, volume='A')
dfs_b = DFS.from_buffer(buffer, format, side=0, volume='B')
```

**Recommendation:** Support both. Provide `set_volume()` for convenience, but users can create multiple instances if preferred.

### 2. Default Volume Behavior

**Question:** What should happen if volume not specified?

**Recommendation:** Default to volume 'A'
- Matches Opus DDOS behavior (`*DRIVE` defaults to A)
- Allows Acorn DFS disks to be read (treated as volume A)
- Simple and predictable

### 3. Cross-Volume Operations

**Question:** Support copying between volumes?

**Recommendation:** Not initially. Users can:
```python
dfs_a = DFS.from_buffer(buffer, format, side=0, volume='A')
dfs_b = DFS.from_buffer(buffer, format, side=0, volume='B')

data = dfs_a.load('$.FILE')
dfs_b.save('$.FILE', data)
```

### 4. Partial Volume Validation

**Question:** Require all 8 volumes valid, or allow partial?

**Recommendation:** Allow partial volumes
- Some disks may only use volumes A-D
- Validation should check allocated volumes, not require all 8
- Empty/unallocated volumes return empty file lists

## Implementation Checklist

### Surface Layer
- [ ] No changes required (18 sectors/track already supported)

### Catalogue Layer
- [ ] Add `supports_volumes` property to `Catalogue` base class
- [ ] Add optional `get_volume()` method to base class
- [ ] Implement `OpusDDOSCatalogue` class
  - [ ] Parse allocation table in sector 16
  - [ ] Create 8 `OpusDDOSVolume` sub-catalog instances
  - [ ] Delegate operations to current volume
  - [ ] Support volume prefix in filenames (`B:$.FILE`)
- [ ] Implement `OpusDDOSVolume` class
  - [ ] Standard DFS catalog parsing (2 sectors)
  - [ ] Logical → physical sector translation
  - [ ] Track-based allocation awareness

### High-Level API
- [ ] Add `volume` parameter to `DFS.__init__()`
- [ ] Add `volume` parameter to `DFS.from_buffer()`
- [ ] Add `set_volume()` method
- [ ] Add `current_volume` property
- [ ] Support volume prefix in file operations

### Format Layer
- [ ] Add `OPUS_DDOS_CATALOGUE_NAME` constant
- [ ] Add Opus DDOS format constants:
  - `OPUS_DDOS_80T_SINGLE_SIDED`
  - `OPUS_DDOS_80T_DOUBLE_SIDED_INTERLEAVED`
  - (40-track variants if needed)

### Testing
- [ ] Unit tests for `OpusDDOSCatalogue`
- [ ] Unit tests for `OpusDDOSVolume`
- [ ] Integration tests with real Opus DDOS images
- [ ] Regression tests (Acorn DFS still works)
- [ ] Volume switching tests
- [ ] Volume prefix parsing tests
- [ ] Partial volume handling tests

### Documentation
- [ ] Update `docs/format-implementation-review.md` with final design
- [ ] Add Opus DDOS examples to README
- [ ] Document volume API in docstrings
- [ ] Add migration guide for Opus DDOS users

## References

- [BeebWiki: Opus DDOS](https://beebwiki.mdfs.net/Opus_DDOS) - Drive and volume addressing
- [Opus DDOS Disassembly](http://regregex.bbcmicro.net/ddos.asm.txt) - ROM source code
- [DDOS2ADFS Utility](https://dr-grim.github.io/retrograde/data%20transfer/Opus-DDOS2ADFS/) - Format conversion tool
- `docs/format-implementation-review.md` - Initial architecture analysis
- `docs/bbc-disc-formats.md` - Technical format specifications

---

**Document Version:** 1.0
**Date:** December 2024
**Status:** Research findings - not yet implemented
**Priority:** Low (pending user decision)

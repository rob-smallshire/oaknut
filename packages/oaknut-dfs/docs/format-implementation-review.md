# DFS Format Variants: Implementation Review

## Executive Summary

This document evaluates the feasibility of adding support for Watford DFS, Watford DDFS, Solidisk DDFS, and Opus DDOS to the oaknut-dfs library. The current architecture is **well-suited** for extension, primarily requiring new `Catalogue` subclasses and `DiskFormat` constants. The sector abstraction layer (`Surface`) already supports variable sectors-per-track through parameterization, eliminating the need for low-level geometry changes.

**Overall Assessment:** The three-layer architecture (Surface → Catalogue → High-level API) provides excellent separation of concerns and is sufficiently flexible to accommodate all four format variants with varying degrees of implementation complexity.

## Current Architecture Review

### Layer 1: Surface (Physical Sector Access)

**Files:** `surface.py`, `formats.py`

**Key Abstractions:**
- `DiscImage`: Container for raw buffer and multiple `SurfaceSpec` definitions
- `SurfaceSpec`: Parameterized geometry specification
  - `num_tracks`: Number of tracks per surface
  - `sectors_per_track`: **Parameterized** - supports 10, 16, 18, or any value
  - `bytes_per_sector`: Typically 256
  - `track_zero_offset_bytes`: Where this surface starts in buffer
  - `track_stride_bytes`: Distance between tracks (supports interleaving)
- `Surface`: Provides `sector_range(start, count)` for contiguous sector access

**Flexibility Assessment:**
- ✅ **Excellent:** Fully parameterized geometry
- ✅ Supports single/double-sided via multiple specs
- ✅ Supports interleaved and sequential layouts
- ✅ No hardcoded assumptions about sectors-per-track
- ✅ Works with any sector count (10, 16, 18, etc.)

**Changes Required:** **NONE** - All format variants can use existing Surface layer

### Layer 2: Catalogue (Catalog Structure)

**Files:** `catalogue.py`, `acorn_dfs_catalogue.py`

**Key Abstractions:**
- `Catalogue`: Abstract base class with registry system
- Subclass registration via `CATALOGUE_NAME` class attribute
- `matches(surface)`: Static heuristic for format identification
- Abstract methods for all catalog operations (read, write, delete, validate, compact)

**Current Implementation:**
- `AcornDFSCatalogue`: Standard Acorn DFS
  - Catalog in sectors 0-1
  - 31 files maximum
  - 10-bit sector addressing
  - 18-bit file lengths and addresses

**Flexibility Assessment:**
- ✅ **Good:** Registry pattern enables multiple catalog types
- ✅ `matches()` heuristic allows automatic format detection
- ✅ Surface-agnostic (works with any geometry)
- ✅ Clear abstraction boundaries

**Changes Required:** **New subclasses** for each variant (detailed below)

### Layer 3: High-Level API

**Files:** `dfs.py`, `catalogued_surface.py`

**Key Abstractions:**
- `CataloguedSurface`: Generic wrapper combining Surface + Catalogue
- `DFS`: User-facing API mirroring BBC Micro commands

**Flexibility Assessment:**
- ✅ **Excellent:** Generic over any Catalogue implementation
- ⚠️ May need minor extensions for partition-based systems (Opus)

**Changes Required:** **Minimal** - Possibly add partition awareness for Opus DDOS

---

## Format-Specific Implementation Analysis

## 1. Watford DFS (62-File Extended Catalog)

### Technical Overview

Watford DFS extends standard Acorn DFS to support 62 files instead of 31 by using sectors 2-3 as a second catalog.

**Physical Characteristics:**
- Sectors per track: **10** (same as Acorn DFS)
- Catalog location: Sectors **0-3** (4 sectors total)
- File capacity: **62 files** (31 in sectors 0-1, 31 in sectors 2-3)
- Addressing: Same as Acorn DFS (10-bit sectors, 18-bit lengths)
- Title: **10 characters** (vs 12 in Acorn) - bytes 10-11 used for chaining

**Detection Markers:**
- Sector 2, bytes 0-11: 12 bytes of **0xAA** (recognition pattern)
- Sector 3, bytes 0-3: **0x00** × 4
- Sector 3, bytes 5-7: Mirror of sector 1 metadata

**Compatibility:**
- Acorn DFS can read first 31 files
- Watford DFS ROM required for full 62-file access

### Implementation Requirements

#### Surface Layer
**Changes:** **NONE**

Watford DFS uses 10 sectors/track, identical to standard Acorn DFS. Existing format constants work as-is.

#### Catalogue Layer
**Changes:** **NEW SUBCLASS** - `WatfordDFSCatalogue`

**File:** `src/oaknut_dfs/watford_dfs_catalogue.py`

```python
class WatfordDFSCatalogue(Catalogue):
    CATALOGUE_NAME = "watford-dfs"
    MAX_FILES = 62
    CATALOG_START_SECTOR = 0
    CATALOG_NUM_SECTORS = 4  # Sectors 0-3

    @classmethod
    def matches(cls, surface: Surface) -> bool:
        """Detect Watford DFS via 0xAA marker in sector 2."""
        if surface.num_sectors < 4:
            return False

        sector2 = surface.sector_range(2, 1)
        # Check for 12 bytes of 0xAA
        if all(sector2[i] == 0xAA for i in range(12)):
            return True
        return False
```

**Key Implementation Details:**

1. **File Listing:**
   - Read sectors 0-1 (first 31 files) - same logic as Acorn DFS
   - Read sectors 2-3 (files 32-62) - identical structure
   - Merge both lists

2. **Add File:**
   - If num_files < 31: Add to sectors 0-1
   - If num_files >= 31: Add to sectors 2-3
   - Keep both catalog copies synchronized

3. **Remove File:**
   - Determine which catalog section contains file
   - Rebuild appropriate catalog section
   - Update both catalogs' metadata

4. **Title Handling:**
   - Limit title to 10 characters (not 12)
   - Bytes 10-11 of sector 0 reserved for catalog linking

5. **Cycle Number:**
   - Increment in both sector 1 and sector 3 on modifications

6. **Validation:**
   - Check both catalog sections for consistency
   - Verify 0xAA marker present
   - Ensure no files span across catalog boundary

7. **Compact:**
   - Standard compact algorithm works
   - Just need to handle 62 files instead of 31

**Code Reuse:**
- Can inherit many methods from `AcornDFSCatalogue`
- Override: `max_files`, `list_files()`, `add_file_entry()`, `remove_file_entry()`, `_rebuild_catalog()`, `matches()`
- Reuse: File entry parsing, address reconstruction, validation logic

#### Format Layer
**Changes:** **NEW CONSTANTS**

**File:** `src/oaknut_dfs/formats.py`

```python
WATFORD_DFS_CATALOGUE_NAME = "watford-dfs"

# Add format constants (same geometry as Acorn DFS)
WATFORD_DFS_40T_SINGLE_SIDED = DiskFormat(
    surface_specs=[_single_sided_spec(TRACKS_40, 10, BYTES_PER_SECTOR)],
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_40T_DOUBLE_SIDED_INTERLEAVED = DiskFormat(
    surface_specs=_interleaved_double_sided_specs(TRACKS_40, 10, BYTES_PER_SECTOR),
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

# ... 80-track variants
```

#### High-Level API
**Changes:** **NONE**

`DFS` class works as-is. Users simply instantiate with Watford format constant:

```python
dfs = DFS.from_buffer(buffer, WATFORD_DFS_40T_SINGLE_SIDED)
```

### Complexity Assessment

**Complexity:** ⭐⭐☆☆☆ **LOW**

**Effort Estimate:** 1-2 days

**Rationale:**
- Catalog structure identical to Acorn DFS, just duplicated
- No new bit-packing schemes
- No address calculation changes
- Primary challenge: Keeping dual catalogs synchronized
- High code reuse from `AcornDFSCatalogue`

### Testing Strategy

1. **Unit Tests:**
   - Format detection (0xAA marker)
   - Adding files to first catalog (1-31)
   - Adding files to second catalog (32-62)
   - Removing files from each catalog section
   - Cross-catalog operations

2. **Integration Tests:**
   - Read existing Watford DFS images
   - Create new 62-file disks
   - Fill to capacity
   - Verify Acorn DFS can read first 31 files

3. **Validation Tests:**
   - Catalog consistency checks
   - Metadata mirroring between sectors 1 and 3

### Risks and Mitigations

**Risk:** Catalog desynchronization
- **Mitigation:** Always update both catalog sections atomically
- **Mitigation:** Add validation check comparing sectors 1 and 3

**Risk:** Title length confusion (10 vs 12 chars)
- **Mitigation:** Override `validate_title()` to enforce 10-char max

---

## 2. Watford DDFS (Double-Density 18 Sectors/Track)

### Technical Overview

Watford DDFS increases storage density to 18 sectors per track, requiring extended addressing.

**Physical Characteristics:**
- Sectors per track: **18** (vs 10 standard)
- Catalog location: Sectors **0-1** (standard)
- File capacity: **31 files** (standard)
- Addressing: **11-bit sectors** (max 2048 sectors = 512KB)
- File lengths: **19-bit** (max 512KB - 1)
- Bit storage: Upper bits stored in disk title and filename fields

**Byte 0x106 Pattern:**
- Bit 3 = **0** (DFS, not HDFS)
- Bit 2 = **1** (indicates >256KB capacity)
- This distinguishes Watford DDFS from standard Acorn DFS

**Bit Stealing Mechanism:**

Watford DDFS repurposes the high bit (bit 7) of title and filename characters:

| Field | Acorn DFS | Watford DDFS |
|-------|-----------|--------------|
| Start sector | 10-bit (byte 0x106 bits 0-1 + byte 0x107) | **11-bit** (bit 2 of byte 0x106 used) |
| File length | 18-bit | **19-bit** (extra bit in title/filename) |
| Title chars | 7-bit ASCII | **6-bit** + 1 extension bit |

When viewed with Acorn DFS ROM, titles/filenames appear garbled (high bits set).

**Capacity Calculations:**
- 80 tracks × 18 sectors/track = 1440 sectors
- 1440 × 256 bytes = **368,640 bytes** (360KB) per side
- Double-sided: **720KB** total

### Implementation Requirements

#### Surface Layer
**Changes:** **NONE**

The `SurfaceSpec` already supports `sectors_per_track=18` as a parameter.

#### Catalogue Layer
**Changes:** **NEW SUBCLASS** - `WatfordDDFSCatalogue`

**File:** `src/oaknut_dfs/watford_ddfs_catalogue.py`

```python
class WatfordDDFSCatalogue(Catalogue):
    CATALOGUE_NAME = "watford-ddfs"
    MAX_FILES = 31
    CATALOG_START_SECTOR = 0
    CATALOG_NUM_SECTORS = 2

    # Extended addressing
    MAX_SECTORS = 2048  # 11-bit addressing
    MAX_FILE_LENGTH = (1 << 19) - 1  # 19-bit file length

    @classmethod
    def matches(cls, surface: Surface) -> bool:
        """Detect Watford DDFS via byte 0x106 bit pattern."""
        if surface.num_sectors < 2:
            return False

        sector1 = surface.sector_range(1, 1)
        boot_sectors_byte = sector1[6]

        # Check bit pattern: b3=0 (DFS), b2=1 (>256KB)
        bit3 = (boot_sectors_byte >> 3) & 1
        bit2 = (boot_sectors_byte >> 2) & 1

        if bit3 == 0 and bit2 == 1:
            # Additional validation: sectors_per_track should be 18
            if surface.sectors_per_track == 18:
                return True

        return False
```

**Key Implementation Details:**

1. **Extended Sector Addressing (11-bit):**

   In Acorn DFS, start sector uses bits 0-1 of byte 0x106:
   ```python
   start_sector = sector1[n×8 + 7] | ((sector1[n×8 + 6] & 0x03) << 8)  # 10-bit
   ```

   Watford DDFS uses bit 2 as well:
   ```python
   start_sector = (sector1[n×8 + 7] |
                   ((sector1[n×8 + 6] & 0x07) << 8))  # 11-bit (bits 0-2)
   ```

2. **Extended File Length (19-bit):**

   Acorn DFS provides 18-bit file lengths via bits 4-5 of byte 0x106:
   ```python
   length = length_low | ((extra_byte & 0x30) << 12)  # 18-bit
   ```

   Watford DDFS needs an additional bit. This is stored in the filename or title bytes by setting bit 7 of certain characters. The exact scheme varies by Watford DDFS version:

   **Option A:** Use bit 7 of first title character
   ```python
   length_bit_18 = (sector0[0] & 0x80) >> 7  # Extract from title
   length = length_low | ((extra_byte & 0x30) << 12) | (length_bit_18 << 18)
   ```

   **Option B:** Use bit 7 of filename characters (per-file)

   Research needed to determine exact bit allocation scheme used by Watford.

3. **Disk Total Sectors (11-bit):**

   Standard DFS uses 10-bit sector count:
   ```python
   total_sectors = sector1[7] | ((sector1[6] & 0x03) << 8)  # 10-bit
   ```

   Watford DDFS uses bit 2:
   ```python
   total_sectors = sector1[7] | ((sector1[6] & 0x07) << 8)  # 11-bit
   ```

4. **Bit Masking/Unmasking:**

   When reading:
   ```python
   # Extract title, clear high bits
   title_raw = bytes(sector0[0:8] + sector1[0:4])
   title = bytes(b & 0x7F for b in title_raw).decode('acorn')
   ```

   When writing:
   ```python
   # Encode title, then set high bits for length extension
   title_bytes = title.encode('acorn')
   if file_length_bit_18:
       title_bytes[0] |= 0x80  # Store length bit 18
   sector0[0:8] = title_bytes[0:8]
   ```

5. **Load/Exec Address:**
   - Same 18-bit addressing as Acorn DFS
   - No extensions needed (addresses don't exceed 256KB boundary)

**Code Reuse:**
- Inherit from `AcornDFSCatalogue`
- Override: `matches()`, `get_disk_info()`, `list_files()`, `add_file_entry()`, `_rebuild_catalog()`
- Modify: Address reconstruction and bit-packing logic
- Reuse: High-level file operations, validation

**Research Required:**
- Exact bit allocation scheme for 19th length bit
- Whether different Watford DDFS versions use different schemes
- Title encoding/decoding with high bits

#### Format Layer
**Changes:** **NEW CONSTANTS**

**File:** `src/oaknut_dfs/formats.py`

```python
WATFORD_DDFS_CATALOGUE_NAME = "watford-ddfs"
WATFORD_DDFS_SECTORS_PER_TRACK = 18

# 40-track Watford DDFS
WATFORD_DDFS_40T_SINGLE_SIDED = DiskFormat(
    surface_specs=[_single_sided_spec(TRACKS_40, 18, BYTES_PER_SECTOR)],
    catalogue_name=WATFORD_DDFS_CATALOGUE_NAME,
)

WATFORD_DDFS_40T_DOUBLE_SIDED_INTERLEAVED = DiskFormat(
    surface_specs=_interleaved_double_sided_specs(TRACKS_40, 18, BYTES_PER_SECTOR),
    catalogue_name=WATFORD_DDFS_CATALOGUE_NAME,
)

# 80-track Watford DDFS (most common)
WATFORD_DDFS_80T_SINGLE_SIDED = DiskFormat(
    surface_specs=[_single_sided_spec(TRACKS_80, 18, BYTES_PER_SECTOR)],
    catalogue_name=WATFORD_DDFS_CATALOGUE_NAME,
)

WATFORD_DDFS_80T_DOUBLE_SIDED_INTERLEAVED = DiskFormat(
    surface_specs=_interleaved_double_sided_specs(TRACKS_80, 18, BYTES_PER_SECTOR),
    catalogue_name=WATFORD_DDFS_CATALOGUE_NAME,
)
```

#### High-Level API
**Changes:** **NONE**

Works transparently with new catalog implementation.

### Complexity Assessment

**Complexity:** ⭐⭐⭐☆☆ **MEDIUM**

**Effort Estimate:** 3-5 days

**Rationale:**
- Extended addressing requires careful bit manipulation
- Bit stealing mechanism requires research and testing
- Need to handle title/filename encoding correctly
- Risk of data corruption if bit packing incorrect
- Moderate code reuse from `AcornDFSCatalogue`

### Testing Strategy

1. **Unit Tests:**
   - 11-bit sector addressing (values > 1024)
   - 19-bit file length encoding/decoding
   - Title encoding with high bits
   - Disk info with >256KB capacity
   - Format detection (byte 0x106 pattern)

2. **Integration Tests:**
   - Read existing Watford DDFS images
   - Write files > 256 sectors
   - Verify file data integrity
   - Test with actual Watford DDFS disk images from archives

3. **Regression Tests:**
   - Ensure Acorn DFS still works
   - Ensure Watford DFS (62-file) still works
   - Format mis-detection scenarios

4. **Compatibility Tests:**
   - Files created should be readable by BeebEm emulator with Watford DDFS ROM
   - Files created by Watford DDFS ROM should be readable by oaknut-dfs

### Risks and Mitigations

**Risk:** Incorrect bit stealing implementation
- **Mitigation:** Study existing Watford DDFS ROM disassembly
- **Mitigation:** Test against known Watford DDFS disk images
- **Mitigation:** Cross-reference with MMB Utils source code

**Risk:** Title/filename corruption
- **Mitigation:** Comprehensive encoding/decoding tests
- **Mitigation:** Validate high bit masking preserves data

**Risk:** Format misidentification
- **Mitigation:** Strengthen `matches()` heuristic with multiple checks
- **Mitigation:** Check both byte 0x106 pattern AND sectors_per_track

### Open Questions

1. Which characters in title/filename store the 19th length bit?
2. Do all Watford DDFS versions use the same bit allocation?
3. How does Watford DDFS handle mixed disks (some files using extension bits, some not)?

**Research Sources:**
- Watford DDFS ROM disassembly
- MMB Utils source code (`watford_ddfs.c` or similar)
- stardot.org.uk forum threads about Watford DDFS

---

## 3. Solidisk DDFS (16 Sectors/Track with Chained Catalogs)

### Technical Overview

Solidisk DDFS uses 16 sectors per track and introduces chained catalogs for unlimited file capacity.

**Physical Characteristics:**
- Sectors per track: **16**
- Catalog location: Sectors **0-1** (primary), **N-N+1** (chained)
- File capacity: **Unlimited** via chaining (31 files per catalog)
- Addressing: **11-bit sectors** (max 2048 sectors = 512KB)
- File lengths: **19-bit** (max 512KB - 1)
- Capacity: 40-track SS = 160KB, 80-track DS = 640KB

**Byte 0x106 Interpretation (File Entries):**

Solidisk reinterprets standard Acorn DFS bits:

| Bits | Acorn DFS | Solidisk DDFS |
|------|-----------|---------------|
| 7-6 | Exec address b17-16 | **Same** |
| 5-4 | File length b17-16 | **Same** |
| 3 | Load address b17 | **File length b18** (extension!) |
| 2 | Load address b16 | **Start sector b10** (extension!) |
| 1-0 | Start sector b9-8 | **Same** |

**Load Address Hack:**
- Load address bits 17-16 **REUSED** from exec address bits 17-16
- Assumes load and exec addresses share same 64KB page
- Incompatible with programs where load/exec differ in top bits

**Chained Catalog Detection:**

Primary catalog (sector 0):
```
if (sector0[0x02] & 0xC0) == 0xC0:
    # Chained catalog present
    next_catalog_sector = (sector0[0x02] & 0x0F) | ((sector0[0x03] & 0x0F) << 4)
```

**Deleted Files:**
- Directory byte set to **0xFF** to mark deletion
- Space NOT reclaimed (no compaction in secondary catalogs)
- Prevents catalog chain breakage

**Invisible Files:**
- Placeholder entries in secondary catalogs
- Filenames use special chars (0x3F, 0xBF)
- Locked flag set to prevent accidental deletion

### Implementation Requirements

#### Surface Layer
**Changes:** **NONE**

`sectors_per_track=16` already supported.

#### Catalogue Layer
**Changes:** **NEW SUBCLASS** - `SolidiskDDFSCatalogue`

**File:** `src/oaknut_dfs/solidisk_ddfs_catalogue.py`

```python
class SolidiskDDFSCatalogue(Catalogue):
    CATALOGUE_NAME = "solidisk-ddfs"
    MAX_FILES = None  # Unlimited via chaining
    CATALOG_START_SECTOR = 0
    CATALOG_NUM_SECTORS = 2  # Per catalog in chain

    # Extended addressing
    MAX_SECTORS = 2048  # 11-bit addressing
    MAX_FILE_LENGTH = (1 << 19) - 1  # 19-bit file length

    @classmethod
    def matches(cls, surface: Surface) -> bool:
        """Detect Solidisk DDFS via chained catalog marker or 16 sectors/track."""
        if surface.num_sectors < 2:
            return False

        sector0 = surface.sector_range(0, 1)

        # Check for chained catalog marker
        if (sector0[0x02] & 0xC0) == 0xC0:
            return True

        # Alternative: Check if 16 sectors/track and valid DFS structure
        if surface.sectors_per_track == 16:
            sector1 = surface.sector_range(1, 1)
            # Basic DFS validation
            if (sector1[5] & 0x07) == 0 and sector1[5] <= 248:
                return True

        return False
```

**Key Implementation Details:**

1. **Extended Sector Addressing (11-bit):**

   ```python
   def _decode_start_sector(self, extra_byte, sector_low):
       """Decode 11-bit start sector using Solidisk scheme."""
       return sector_low | ((extra_byte & 0x03) << 8) | ((extra_byte & 0x04) << 8)
       # Bits 0-1: Standard b9-b8
       # Bit 2: Solidisk b10
   ```

2. **Extended File Length (19-bit):**

   ```python
   def _decode_length(self, length_low, extra_byte):
       """Decode 19-bit file length using Solidisk scheme."""
       return (length_low |
               ((extra_byte & 0x30) << 12) |  # Standard b17-b16
               ((extra_byte & 0x08) << 15))    # Solidisk b18 (bit 3)
   ```

3. **Load Address Reconstruction:**

   Solidisk reuses exec address high bits for load address:
   ```python
   def _decode_load_address(self, load_low, exec_low, extra_byte):
       """Decode load address by borrowing exec address high bits."""
       exec_high = (extra_byte & 0xC0) >> 6  # Exec bits 17-16
       # Assumption: load and exec share same 64KB page
       load_address = load_low | (exec_high << 16)
       return load_address
   ```

4. **Catalog Chain Traversal:**

   ```python
   def list_files(self) -> list[FileEntry]:
       """List files across all chained catalogs."""
       all_files = []
       catalog_sector = 0

       while catalog_sector is not None:
           # Read catalog at catalog_sector, catalog_sector+1
           files = self._read_catalog_at(catalog_sector)

           # Filter out deleted files (directory == 0xFF)
           active_files = [f for f in files if ord(f.directory) != 0xFF]

           # Filter out invisible placeholders (0x3F, 0xBF in directory)
           visible_files = [f for f in active_files
                           if ord(f.directory) not in (0x3F, 0xBF)]

           all_files.extend(visible_files)

           # Check for next catalog in chain
           sector0 = self._surface.sector_range(catalog_sector, 1)
           if (sector0[0x02] & 0xC0) == 0xC0:
               catalog_sector = ((sector0[0x02] & 0x0F) |
                                ((sector0[0x03] & 0x0F) << 4))
           else:
               catalog_sector = None

       return all_files
   ```

5. **Adding Files to Chained Catalogs:**

   ```python
   def add_file_entry(self, filename, directory, load_address, exec_address,
                      length, start_sector, locked=False):
       """Add file, creating new catalog if current full."""
       # Find catalog with space (traverse chain)
       catalog_sector = self._find_catalog_with_space()

       if catalog_sector is None:
           # All catalogs full - create new catalog
           catalog_sector = self._allocate_new_catalog()

       # Add entry to catalog at catalog_sector
       self._add_entry_to_catalog(catalog_sector, ...)
   ```

6. **Deleting Files (Mark as Deleted):**

   ```python
   def remove_file_entry(self, filename):
       """Mark file as deleted (0xFF) without reclaiming space."""
       entry, catalog_sector = self._find_file_and_catalog(filename)

       if entry.locked:
           raise PermissionError(f"File is locked: {filename}")

       # Mark as deleted by setting directory byte to 0xFF
       sector0 = self._surface.sector_range(catalog_sector, 1)
       entry_offset = 8 + (entry_index * 8)
       sector0[entry_offset + 7] = 0xFF
   ```

7. **Title Limitation:**

   Chained catalogs use bytes 2-3 of title for chain pointer:
   ```python
   def validate_title(self, title):
       """Validate title (max 10 chars for chained catalogs)."""
       if len(title) > 10:
           raise ValueError(f"Title too long: max 10 chars for Solidisk DDFS")
   ```

8. **Validation:**

   ```python
   def validate(self):
       """Validate all catalogs in chain."""
       errors = []

       # Traverse catalog chain
       catalog_sectors = self._get_all_catalog_sectors()

       # Check for catalog chain loops
       if len(catalog_sectors) != len(set(catalog_sectors)):
           errors.append("Catalog chain contains loop")

       # Validate each catalog
       for cat_sector in catalog_sectors:
           errors.extend(self._validate_catalog_at(cat_sector))

       return errors
   ```

**Code Reuse:**
- Inherit from `AcornDFSCatalogue`? NO - too many differences
- Better to implement from `Catalogue` base class
- Reuse: Filename parsing, directory validation
- Override: Almost all catalog operations due to chaining

#### Format Layer
**Changes:** **NEW CONSTANTS**

**File:** `src/oaknut_dfs/formats.py`

```python
SOLIDISK_DDFS_CATALOGUE_NAME = "solidisk-ddfs"
SOLIDISK_DDFS_SECTORS_PER_TRACK = 16

# Solidisk DDFS formats
SOLIDISK_DDFS_40T_SINGLE_SIDED = DiskFormat(
    surface_specs=[_single_sided_spec(TRACKS_40, 16, BYTES_PER_SECTOR)],
    catalogue_name=SOLIDISK_DDFS_CATALOGUE_NAME,
)

SOLIDISK_DDFS_80T_DOUBLE_SIDED_INTERLEAVED = DiskFormat(
    surface_specs=_interleaved_double_sided_specs(TRACKS_80, 16, BYTES_PER_SECTOR),
    catalogue_name=SOLIDISK_DDFS_CATALOGUE_NAME,
)
```

#### High-Level API
**Changes:** **MINOR**

May want to add `max_files` property handling:

```python
@property
def max_files(self) -> int | None:
    """Maximum files (None if unlimited)."""
    max_files = self._catalogued_surface.catalogue.max_files
    return max_files if max_files != float('inf') else None
```

### Complexity Assessment

**Complexity:** ⭐⭐⭐⭐☆ **MEDIUM-HIGH**

**Effort Estimate:** 5-7 days

**Rationale:**
- Chained catalog system is complex
- Multiple catalog traversal required for all operations
- Different bit packing than Acorn/Watford
- Load address hack introduces constraints
- Deleted file handling (no reclamation)
- Minimal code reuse from existing catalogs
- Extensive testing needed for chain integrity

### Testing Strategy

1. **Unit Tests:**
   - 11-bit sector addressing
   - 19-bit file length encoding
   - Load address reconstruction from exec address
   - Catalog chain detection and traversal
   - Adding files across multiple catalogs
   - Deleting files (0xFF marking)
   - Chain pointer extraction

2. **Integration Tests:**
   - Create disk with >31 files (test chaining)
   - Read existing Solidisk DDFS images
   - Verify catalog chain integrity
   - Test with invisible placeholder files
   - Load address edge cases (different pages)

3. **Regression Tests:**
   - Ensure format detection doesn't misidentify other formats
   - Test with 16 sectors/track non-Solidisk disks

4. **Stress Tests:**
   - Create very long catalog chains (100+ files)
   - Verify performance with deep chains
   - Test chain loop detection

### Risks and Mitigations

**Risk:** Catalog chain corruption
- **Mitigation:** Atomic chain pointer updates
- **Mitigation:** Validation checks for loops
- **Mitigation:** Backup catalog before modifications

**Risk:** Load address incompatibility
- **Mitigation:** Document limitation clearly
- **Mitigation:** Warn if load/exec addresses differ in top bits
- **Mitigation:** Consider validation check

**Risk:** Format misidentification (16 sectors could be other formats)
- **Mitigation:** Check for chain marker (0xC0) as primary indicator
- **Mitigation:** Fallback to sectors_per_track check
- **Mitigation:** Order detection to try other 16-sector formats first

**Risk:** Deleted file accumulation
- **Mitigation:** Provide compact operation to rebuild without deleted entries
- **Mitigation:** Document that deleted files consume catalog space

### Open Questions

1. How do different Solidisk DDFS ROM versions handle catalog allocation?
2. What happens when a secondary catalog fills up with deleted files?
3. Is there a maximum chain depth?
4. How are invisible files created and managed?

**Research Sources:**
- Solidisk DDFS ROM disassembly
- stardot.org.uk thread about Solidisk format
- Real Solidisk DDFS disk images from archives

---

## 4. Opus DDOS (Partitioned Multi-Volume Format)

### Technical Overview

Opus DDOS uses a **fundamentally different** architecture with partitioning instead of a single linear catalog.

**Physical Characteristics:**
- Sectors per track: **18**
- Track 0 layout:
  - Sectors 0-15: **8 volume catalogs** (2 sectors each: A-H)
  - Sector 16: **Disc allocation table**
  - Sector 17: Reserved/unused
- File capacity: **248 files per side** (31 × 8 volumes), **992 files total** (double-sided)
- Partition size: Each volume max **252KB** (0x3F0 sectors = 63 tracks)
- Allocation unit: **Track-based** (4.5KB per track)

**Volumes (Sub-Drives):**
- Drive 0: Volumes **0A-0H** (8 volumes)
- Drive 2: Volumes **2A-2H** (8 volumes)
- BBC Micro sees each volume as a separate logical drive

**Disc Allocation Table (Sector 16):**

```
Offset   Length   Field
------   ------   -----
0x00     1        Config byte (0x00=EDOS 0.4, 0x20=DDOS 3.45)
0x01     2        Disk size in sectors (0x5A0 for 80-track DD)
0x03     1        Sectors per track (0x12 = 18)
0x04     1        Density flag
0x05     3        Reserved
0x08     1        Volume A starting track
0x09     1        Volume B starting track
...
0x0F     1        Volume H starting track
0x10     240      Additional allocation data
```

**Volume Catalog Structure:**
- Each volume: Standard DFS-style catalog in 2 sectors
- Sector 0 = **first data sector** (catalog outside volume partition)
- Relative sector numbering within each volume

**Key Difference from Standard DFS:**
- NO single catalog in sectors 0-1 covering whole disk
- Sectors 0-1 contain Volume **A** catalog
- Other volumes have catalogs at sectors 2-3, 4-5, etc.
- Completely incompatible with Acorn DFS ROM

### Implementation Requirements

#### Surface Layer
**Changes:** **NONE**

`sectors_per_track=18` already supported.

#### Catalogue Layer
**Changes:** **NEW SUBCLASS** - `OpusDDOSCatalogue`

**File:** `src/oaknut_dfs/opus_ddos_catalogue.py`

**Architecture Decision:**

Should `OpusDDOSCatalogue` represent:
1. **Option A:** The entire disk (all 8 volumes)
2. **Option B:** A single volume (one catalog)

**Recommendation: Option B (Single Volume)**

Rationale:
- Matches BBC Micro behavior (each volume = separate drive)
- Cleaner abstraction (one catalog = one volume)
- Allows operations on individual volumes
- User specifies which volume when opening disk

However, this requires architecture changes...

**Alternative: Option A (Entire Disk)**

Manage all 8 volumes within one catalog class:
- `list_files(volume='A')` - list files in specific volume
- `find_file(filename, volume='A')` - find in specific volume
- Track current volume context

**Proposed Hybrid Approach:**

Create two classes:
1. `OpusDDOSVolumeCatalogue` - Single volume catalog (inherits standard catalog interface)
2. `OpusDDOSDiscCatalogue` - Wrapper managing all volumes

**File:** `src/oaknut_dfs/opus_ddos_catalogue.py`

```python
class OpusDDOSVolumeCatalogue(Catalogue):
    """
    Single Opus DDOS volume catalog.

    Represents one volume (A-H) on an Opus DDOS disc.
    """
    CATALOGUE_NAME = "opus-ddos-volume"
    MAX_FILES = 31

    def __init__(self, surface: Surface, volume_letter: str, volume_start_track: int):
        """
        Initialize Opus volume catalog.

        Args:
            surface: Disc surface
            volume_letter: Volume letter (A-H)
            volume_start_track: Starting track for this volume
        """
        super().__init__(surface)
        self._volume_letter = volume_letter
        self._volume_start_track = volume_start_track

        # Calculate catalog sectors for this volume
        volume_index = ord(volume_letter) - ord('A')  # 0-7
        self.CATALOG_START_SECTOR = volume_index * 2  # 0,2,4,...,14
        self.CATALOG_NUM_SECTORS = 2

    @property
    def volume_letter(self) -> str:
        return self._volume_letter

    # Standard catalog operations work on this single volume
    def list_files(self) -> list[FileEntry]:
        """List files in this volume."""
        # Read catalog at CATALOG_START_SECTOR
        # Standard DFS-style parsing
        ...

    def _logical_to_physical_sector(self, logical_sector: int) -> int:
        """
        Convert volume-relative sector to disc-absolute sector.

        Opus DDOS uses track-based allocation:
        - Sector 0 in volume = first data sector
        - Physical track = volume_start_track + (sector // 18)
        - Physical sector = track * 18 + (sector % 18)
        """
        track_offset = logical_sector // 18
        sector_in_track = logical_sector % 18
        physical_track = self._volume_start_track + track_offset
        physical_sector = physical_track * 18 + sector_in_track
        return physical_sector


class OpusDDOSDiscCatalogue(Catalogue):
    """
    Complete Opus DDOS disc with multiple volumes.

    Manages all 8 volumes (A-H) on a disc surface.
    """
    CATALOGUE_NAME = "opus-ddos"
    MAX_FILES = 248  # 31 files × 8 volumes
    CATALOG_START_SECTOR = 0
    CATALOG_NUM_SECTORS = 18  # Track 0 (0-15 catalogs + 16 alloc table + 17 reserved)

    def __init__(self, surface: Surface):
        super().__init__(surface)
        self._volumes = {}
        self._load_allocation_table()

    def _load_allocation_table(self):
        """Read disc allocation table from sector 16."""
        sector16 = self._surface.sector_range(16, 1)

        self.config_byte = sector16[0]
        self.disk_size = sector16[1] | (sector16[2] << 8)
        self.sectors_per_track = sector16[3]
        self.density = sector16[4]

        # Read volume start tracks
        for i, letter in enumerate('ABCDEFGH'):
            start_track = sector16[0x08 + i]
            self._volumes[letter] = OpusDDOSVolumeCatalogue(
                self._surface, letter, start_track
            )

    @classmethod
    def matches(cls, surface: Surface) -> bool:
        """Detect Opus DDOS via config byte in sector 16."""
        if surface.num_sectors < 17:
            return False

        # Must be 18 sectors/track
        if surface.sectors_per_track != 18:
            return False

        sector16 = surface.sector_range(16, 1)
        config_byte = sector16[0]

        # Check for known Opus config bytes
        if config_byte in (0x00, 0x20):
            # Additional validation: check disk size and sectors/track
            disk_size = sector16[1] | (sector16[2] << 8)
            spt = sector16[3]

            if spt == 18 and 1000 <= disk_size <= 2000:
                return True

        return False

    def get_volume(self, letter: str) -> OpusDDOSVolumeCatalogue:
        """Get catalog for specific volume."""
        if letter not in self._volumes:
            raise ValueError(f"Invalid volume: {letter}. Must be A-H")
        return self._volumes[letter]

    def list_files(self, volume: str | None = None) -> list[FileEntry]:
        """
        List files from specified volume or all volumes.

        Args:
            volume: Volume letter (A-H) or None for all

        Returns:
            List of file entries (with volume prefix in path)
        """
        if volume:
            return self.get_volume(volume).list_files()

        # List all files from all volumes
        all_files = []
        for letter in 'ABCDEFGH':
            vol_files = self._volumes[letter].list_files()
            # Prefix filenames with volume letter
            for entry in vol_files:
                entry.directory = f"{letter}:{entry.directory}"
            all_files.extend(vol_files)
        return all_files

    # Delegate operations to specific volume
    def find_file(self, filename: str) -> Optional[FileEntry]:
        """Find file (must specify volume prefix like 'A:$.FILE')."""
        if ':' in filename:
            volume, path = filename.split(':', 1)
            return self.get_volume(volume).find_file(path)
        else:
            # Search all volumes
            for vol in self._volumes.values():
                entry = vol.find_file(filename)
                if entry:
                    return entry
            return None
```

**Format Detection:**

Primary marker: Config byte in sector 16
- Must be 0x00 or 0x20
- Sectors per track must be 18
- Disk size reasonable (1000-2000 sectors)

**Volume Operations:**

File operations require volume context:

```python
# Read file from specific volume
data = opus_catalog.get_volume('A').read_file('$.HELLO')

# Or use volume prefix
data = opus_catalog.read_file('A:$.HELLO')
```

#### Format Layer
**Changes:** **NEW CONSTANTS**

**File:** `src/oaknut_dfs/formats.py`

```python
OPUS_DDOS_CATALOGUE_NAME = "opus-ddos"
OPUS_DDOS_SECTORS_PER_TRACK = 18

# Opus DDOS formats (usually 80-track)
OPUS_DDOS_80T_SINGLE_SIDED = DiskFormat(
    surface_specs=[_single_sided_spec(TRACKS_80, 18, BYTES_PER_SECTOR)],
    catalogue_name=OPUS_DDOS_CATALOGUE_NAME,
)

OPUS_DDOS_80T_DOUBLE_SIDED_INTERLEAVED = DiskFormat(
    surface_specs=_interleaved_double_sided_specs(TRACKS_80, 18, BYTES_PER_SECTOR),
    catalogue_name=OPUS_DDOS_CATALOGUE_NAME,
)
```

#### High-Level API
**Changes:** **MODERATE**

Need to add volume awareness:

**Option 1: Explicit Volume Parameter**

```python
class DFS:
    def load(self, filename: str, volume: str | None = None) -> bytes:
        """Load file, optionally specifying volume."""
        if volume:
            return self._catalogued_surface.catalogue.get_volume(volume).read_file(filename)
        return self._catalogued_surface.read_file(filename)
```

**Option 2: Volume Prefix in Filename**

```python
# User includes volume in filename
data = dfs.load('A:$.HELLO')  # Load from volume A
data = dfs.load('B:$.DATA')   # Load from volume B
```

**Option 3: Separate DFS Instance Per Volume**

```python
# Create DFS for specific volume
dfs_a = DFS.from_buffer(buffer, OPUS_DDOS_80T_SINGLE_SIDED, volume='A')
dfs_b = DFS.from_buffer(buffer, OPUS_DDOS_80T_SINGLE_SIDED, volume='B')
```

**Recommendation: Option 2 (Volume Prefix)**
- Most transparent to user
- Matches Opus DDOS conventions
- No API changes needed (just parsing logic)

### Complexity Assessment

**Complexity:** ⭐⭐⭐⭐⭐ **HIGH**

**Effort Estimate:** 7-10 days

**Rationale:**
- Fundamentally different architecture (partitioned vs linear)
- Track-based allocation instead of sector-based
- Multiple catalogs to manage
- Disc allocation table parsing and management
- Volume abstraction layer needed
- Sector address translation (logical → physical)
- High-level API changes for volume awareness
- Minimal code reuse (completely different catalog structure)
- Extensive testing across all volumes

### Testing Strategy

1. **Unit Tests:**
   - Allocation table parsing
   - Volume catalog detection
   - Logical to physical sector translation
   - Volume-specific file operations
   - Multi-volume file listing
   - Config byte validation

2. **Integration Tests:**
   - Read existing Opus DDOS images
   - Create files in different volumes
   - Verify volume isolation
   - Test allocation table updates
   - Cross-volume operations

3. **Compatibility Tests:**
   - Files should be readable in BeebEm with Opus DDOS ROM
   - Test with actual Opus DDOS disk images

4. **Edge Cases:**
   - Empty volumes
   - Full volumes
   - Invalid volume letters
   - Sector overflow within volume

### Risks and Mitigations

**Risk:** Complex volume/partition management
- **Mitigation:** Clear abstraction with `OpusDDOSVolumeCatalogue`
- **Mitigation:** Extensive documentation of volume system

**Risk:** Sector translation errors
- **Mitigation:** Comprehensive unit tests for address mapping
- **Mitigation:** Validate against known disk images

**Risk:** Format misidentification (18 sectors/track like Watford DDFS)
- **Mitigation:** Check sector 16 config byte as PRIMARY indicator
- **Mitigation:** Detection order: Opus first (sector 16), then Watford DDFS

**Risk:** API inconsistency with other formats
- **Mitigation:** Make volume prefix optional (default to volume A)
- **Mitigation:** Document Opus-specific behavior clearly

### Open Questions

1. How does Opus DDOS handle cross-volume operations?
2. Can files span multiple volumes? (Unlikely but worth checking)
3. What happens when a volume is full?
4. How are volume start tracks allocated dynamically?
5. Is the allocation table updated when adding files, or only when formatting?

**Research Sources:**
- Opus DDOS user manual
- BeebWiki Opus DDOS page (already reviewed)
- Opus DDOS ROM disassembly
- MMB Utils Opus handling code

---

## Summary and Recommendations

### Feasibility Assessment

| Format | Complexity | Effort | Architecture Changes | Recommended Priority |
|--------|-----------|--------|---------------------|---------------------|
| Watford DFS | LOW ⭐⭐ | 1-2 days | New catalog subclass | **HIGH** - Easy win |
| Watford DDFS | MEDIUM ⭐⭐⭐ | 3-5 days | New catalog subclass | **MEDIUM** - Moderate complexity |
| Solidisk DDFS | MEDIUM-HIGH ⭐⭐⭐⭐ | 5-7 days | New catalog subclass | **MEDIUM** - Chain management |
| Opus DDOS | HIGH ⭐⭐⭐⭐⭐ | 7-10 days | New catalog + API changes | **LOW** - Major refactoring |

### Overall Verdict

**Is the architecture sufficiently flexible?**

**YES** - with caveats:

✅ **Surface Layer:** Fully flexible. No changes needed for any format.

✅ **Catalogue Layer:** Well-designed with registry pattern and abstract interface. New subclasses integrate seamlessly.

⚠️ **High-Level API:** Mostly flexible, but Opus DDOS may require volume awareness additions.

### Recommended Implementation Order

1. **Watford DFS (62-file)**
   - Lowest complexity
   - Validates catalog extension pattern
   - High user value
   - Foundation for understanding dual catalogs

2. **Watford DDFS OR Solidisk DDFS**
   - Similar complexity (both need extended addressing)
   - Choose based on user demand
   - Watford DDFS: More common, better documented
   - Solidisk DDFS: More interesting technically (chaining)

3. **Remaining DDFS Format**
   - Complete double-density support

4. **Opus DDOS**
   - Highest complexity
   - Requires API changes
   - Lowest user demand (niche format)
   - Consider as future enhancement

### Key Success Factors

1. **Research First:**
   - Study ROM disassemblies
   - Analyze real disk images
   - Cross-reference with existing tools (MMB Utils, BeebEm)

2. **Test-Driven Development:**
   - Write tests against known disk images
   - Verify compatibility with emulators
   - Test format detection carefully

3. **Documentation:**
   - Document bit-packing schemes clearly
   - Explain format-specific limitations
   - Provide migration guides

4. **Backward Compatibility:**
   - Ensure existing Acorn DFS code unaffected
   - Test all formats after each addition
   - Regression test suite

### Potential Architecture Improvements

While the current architecture is flexible, consider these enhancements:

1. **Format Detection Pipeline:**
   - Order matters for overlapping detection patterns
   - Consider explicit detection priority configuration
   - Add confidence scoring to `matches()` method

2. **Catalog Capabilities Interface:**
   - Some catalogs support unlimited files (Solidisk)
   - Some support volumes (Opus)
   - Consider capabilities pattern for format-specific features

3. **Sector Translation Layer:**
   - Opus needs logical → physical sector mapping
   - Consider formalizing this in Catalogue base class

4. **Error Handling:**
   - Format-specific validation errors
   - Better error messages distinguishing format issues

---

**Document Version:** 1.0
**Date:** December 2024
**Author:** oaknut-dfs project

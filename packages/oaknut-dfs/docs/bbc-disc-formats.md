# BBC Micro Disc Format Technical Reference

## Introduction

This document provides comprehensive technical specifications for various BBC Micro disc formats, with particular emphasis on features that enable automatic format identification and validation. The information herein supports implementing robust disk image detection heuristics for tools handling Acorn DFS and its variants.

### Scope

This document covers:
- **Acorn DFS**: Standard single and double-density formats
- **Watford DFS**: 62-file catalog extension
- **Watford DDFS**: Double-density format with extended addressing
- **Solidisk DDFS**: Double-density format with chained catalogs
- **Opus DDOS**: Partitioned double-density format
- **MMB Container**: Multi-disc image container format for SD card storage

### Purpose

The primary goals are to:
1. Document byte-level catalog structures for each format variant
2. Provide file size tables for geometry detection
3. Establish validation heuristics for format identification
4. Clarify ambiguous cases and edge conditions
5. Enable implementation of automatic format detection algorithms

## Physical Format Specifications

### Fundamental Constants

All DFS variants share these basic parameters:
- **Sector size**: 256 bytes (constant across all formats)
- **Catalog location**: Sectors 0-1 (track 0, with format-specific variations)
- **Track numbering**: 0-indexed (0-39 for 40-track, 0-79 for 80-track)
- **Sector numbering**: 0-indexed within each track

### Format Comparison Table

| Format | Sectors/Track | Density | Typical Tracks | Sides | Capacity (40T) | Capacity (80T) | Max Files |
|--------|---------------|---------|----------------|-------|----------------|----------------|-----------|
| Acorn DFS | 10 | SD | 40 or 80 | 1 or 2 | 100KB / 200KB | 200KB / 400KB | 31 |
| Watford DFS | 10 | SD | 40 or 80 | 1 or 2 | 100KB / 200KB | 200KB / 400KB | 62 |
| Watford DDFS | 18 | DD | 40 or 80 | 1 or 2 | 180KB / 360KB | 360KB / 720KB | 31 |
| Solidisk DDFS | 16 | DD | 40 or 80 | 1 or 2 | 160KB / 320KB | 320KB / 640KB | 31+ |
| Opus DDOS | 18 | DD | 40 or 80 | 1 or 2 | 180KB / 360KB | 360KB / 720KB | 248 |

### File Size Table (for Format Detection)

This table maps file sizes to possible format combinations:

| File Size (bytes) | Calculation | Possible Formats |
|------------------|-------------|------------------|
| 102,400 | 40 × 1 × 10 × 256 | SSD 40-track |
| 163,840 | 40 × 1 × 16 × 256 | Solidisk SSD 40-track |
| 184,320 | 40 × 1 × 18 × 256 | Watford/Opus SSD 40-track |
| 204,800 | 80 × 1 × 10 × 256 **OR** 40 × 2 × 10 × 256 | SSD 80-track **OR** DSD 40-track ⚠️ |
| 327,680 | 80 × 1 × 16 × 256 **OR** 40 × 2 × 16 × 256 | Solidisk SSD 80-track OR DSD 40-track |
| 368,640 | 80 × 1 × 18 × 256 **OR** 40 × 2 × 18 × 256 | Watford/Opus SSD 80-track OR DSD 40-track |
| 409,600 | 80 × 2 × 10 × 256 | DSD 80-track |
| 655,360 | 80 × 2 × 16 × 256 | Solidisk DSD 80-track |
| 737,280 | 80 × 2 × 18 × 256 | Watford/Opus DSD 80-track |

⚠️ **Ambiguity Alert**: 204,800 bytes is ambiguous - requires catalog inspection to distinguish.

### Interleaving Schemes

**SSD (Single-Sided, Sequential)**
- Sectors stored sequentially: Track 0 Sector 0, 1, 2...9, Track 1 Sector 0, 1, 2...9, etc.
- Physical offset = `track × sectors_per_track × 256 + sector × 256`

**DSD (Double-Sided, Interleaved)**
- Default mode: Tracks alternate between sides: T0S0, T0S1, T1S0, T1S1, T2S0, T2S1...
- Physical offset calculation more complex (see sector_image.py in oaknut-dfs)
- Logical sector number maps to (track, side, sector_within_track)

**DSD (Double-Sided, Sequential/Concatenated)**
- Alternative layout: All tracks of side 0 first, then all tracks of side 1
- Side 0: T0, T1, T2...T39/79 sequentially
- Side 1: T0, T1, T2...T39/79 sequentially after side 0
- Less common than interleaved format but supported by some tools

## Catalog Structure: Standard Acorn DFS

### Sectors 0-1 Layout

The catalog occupies the first two sectors (512 bytes total) with entries split across both:

**Sector 0 (First 256 bytes)**
```
Offset   Length   Field
------   ------   -----
0x00     8        Disk title (first 8 chars)
0x08     8        File 1: filename (7 chars) + directory char (byte 7, bits 0-6)
0x08     1        File 1: locked flag (byte 7, bit 7)
0x10     8        File 2: filename + directory + locked
...
0xF8     8        File 31: filename + directory + locked
```

**Sector 1 (Second 256 bytes)**
```
Offset   Length   Field
------   ------   -----
0x00     4        Disk title (last 4 chars)
0x04     1        Disk cycle number (BCD)
0x05     1        Number of files × 8
0x06     1        Boot option (bits 4-5) + sector count high bits (bits 0-3)
0x07     1        Sector count low 8 bits
0x08     8        File 1: load addr (2) + exec addr (2) + length (2) + extra (1) + start sector (1)
0x10     8        File 2: metadata
...
0xF8     8        File 31: metadata
```

### Byte 0x106 Structure (Critical!)

This byte at offset 0x106 in sector 1 (byte 6 overall) has dual purposes:

**When in disk header (first entry, offset 0x106)**
```
Bit 7-6: Reserved (must be 0)
Bit 5-4: Boot option (*OPT 4,n value)
        00 = No action
        01 = *LOAD $.!BOOT
        10 = *RUN $.!BOOT
        11 = *EXEC $.!BOOT
Bit 3:   File system type
        0 = DFS or Watford DFS
        1 = HDFS (Hierarchical DFS)
Bit 2:   Sector count bit 10 (or HDFS: number of sides - 1)
Bit 1-0: Sector count bits 9-8
```

**When in file entry (offset 0x106 + n×8 for file n)**
```
Bit 7-6: Exec address bits 17-16
Bit 5-4: File length bits 17-16
Bit 3-2: Load address bits 17-16
Bit 1-0: Start sector bits 9-8
```

### File Entry Details

Each file entry uses 8 bytes in sector 0 and 8 bytes in sector 1:

**Sector 0 portion (8 bytes at offset 0x08 + n×8)**
```
Byte 0-6: Filename (7 characters, Acorn encoding)
          Allowed: 0x20-0x7E except space, . : " # *
Byte 7:   bits 0-6: Directory character (single letter)
          bit 7: Locked flag (1 = locked)
```

**Sector 1 portion (8 bytes at offset 0x08 + n×8)**
```
Byte 0-1: Load address bits 15-0 (little-endian)
Byte 2-3: Exec address bits 15-0 (little-endian)
Byte 4-5: File length bits 15-0 (little-endian)
Byte 6:   Extended bits (see byte 0x106 structure above)
Byte 7:   Start sector bits 7-0
```

### Address and Length Reconstruction

To reconstruct 18-bit values from the catalog:

**Load Address (18-bit)**
```
load_addr = (sector1[n×8 + 0]) | (sector1[n×8 + 1] << 8) | ((sector1[n×8 + 6] & 0x0C) << 14)
```

**Exec Address (18-bit)**
```
exec_addr = (sector1[n×8 + 2]) | (sector1[n×8 + 3] << 8) | ((sector1[n×8 + 6] & 0xC0) << 10)
```

**File Length (18-bit)**
```
length = (sector1[n×8 + 4]) | (sector1[n×8 + 5] << 8) | ((sector1[n×8 + 6] & 0x30) << 12)
```

**Start Sector (10-bit)**
```
start_sector = sector1[n×8 + 7] | ((sector1[n×8 + 6] & 0x03) << 8)
```

### Catalog Validation Rules

A valid Acorn DFS catalog must satisfy:

1. **File count constraint**: Byte 0x105 must be ≤ 248 (31 files × 8)
2. **File count multiple**: Byte 0x105 must be multiple of 8
3. **Sector count range**: Total sectors (10-bit) must be ≥ 2 and ≤ 800
4. **Reserved bits**: Bits 7-6 of byte 0x106 must be 0
5. **File ordering**: Files must appear in descending start sector order
6. **No overlap**: No two files may occupy the same sectors
7. **Catalog protection**: Files must not overlap sectors 0-1
8. **Sector bounds**: All file sectors must be within disk bounds

## Format-Specific Variants

### Watford DFS (62-File Catalog)

Watford DFS extends the catalog to sectors 2-3, doubling file capacity.

**Identification Method**
- Check sectors 2-3 for the pattern: 12 consecutive bytes of 0xAA
- Location: Sector 2, offset 0x00-0x0B (first 12 bytes)

**Structure**
- Sectors 0-1: Identical to Acorn DFS (first 31 files)
- Sectors 2-3: Mirror layout of sectors 0-1 (files 32-62)
- Boot option and disk size duplicated in both catalog pairs

**Compatibility**
- Acorn DFS can read first 31 files only
- Full 62-file access requires Watford DFS ROM

**Disk Title Constraint**
- Title limited to 10 characters (vs. 12 in standard DFS)
- Bytes 10-11 used for catalog chaining information

### Watford DDFS (Double Density)

Watford's double-density format increases sectors per track to 18.

**Physical Parameters**
- 18 sectors/track
- 256 bytes/sector
- 40 or 80 tracks
- Single or double-sided

**Extended Addressing**
- 19-bit file lengths (max 512KB - 1)
- 11-bit sector numbers (max 2048 sectors)
- Extra bits stored in upper bits of disk title and filename fields

**Byte 0x106 Identification**
```
Bit 3 = 0 (DFS, not HDFS)
Bit 2 = 1 (indicates >256KB capacity)
```

**Bit Stealing Mechanism**
- Upper bits of ASCII characters in title/filenames repurposed
- Standard Acorn DFS would show garbled characters if it could read them
- Watford DDFS ROM masks/unmasks these bits appropriately

### Solidisk DDFS (16 Sectors/Track)

Solidisk's format uses 16 sectors per track and introduces chained catalogs.

**Physical Parameters**
- 16 sectors/track
- 40 or 80 tracks
- Capacity: 160KB (40-track SS) to 640KB (80-track DS)

**Byte 0x106 Extensions (File Entries)**

Solidisk reinterprets bits in byte 0x106 differently than Acorn:

```
Bit 7-6: Exec address bits 17-16 (standard)
Bit 5-4: File length bits 17-16 (standard)
Bit 3:   File length bit 18 (Solidisk extension!)
Bit 2:   Start sector bit 10 (Solidisk extension!)
Bit 1-0: Start sector bits 9-8 (standard)
```

This provides:
- 11-bit start sector (vs. 10-bit standard)
- 19-bit file length (vs. 18-bit standard)

**Load Address Bit Reuse**

Solidisk reuses exec address high bits for load address:
- Load address bits 17-16 taken from exec address bits 17-16
- Assumes load and exec addresses share the same high bits (true for most BBC programs)
- Incompatible with programs where load/exec are in different 64KB pages

**Chained Catalogs**

Solidisk supports unlimited files via catalog chaining:

**Detection**
```
if (sector0[0x02] & 0xC0) == 0xC0:
    # This is a chained catalog
    catalog_pointer = (sector0[0x02] & 0x0F) | ((sector0[0x03] & 0x0F) << 4)
```

**Structure**
- Byte 2, bits 7-6 = 11 indicates chained catalog
- Bytes 2-3 (lower nibbles) contain pointer to next catalog sector
- Each secondary catalog holds 30 files (preserving entries for linking)
- Title reduced to 10 characters to accommodate chain pointers

**Invisible Files**

Secondary catalogs may contain "invisible" locked placeholder entries:
- Filenames use special characters (0x3F, 0xBF)
- Locked flag set to prevent deletion
- Preserve catalog chain structure when files deleted

**Deleted Files in Chained Catalogs**

Unlike standard DFS, Solidisk doesn't reclaim space when files are deleted from chained catalogs:
- Directory byte set to 0xFF to mark file as deleted
- Entry remains in catalog but is hidden
- Space not compacted or reused for new files
- Secondary catalog structure preserved

**Format Misidentification Issues**

Solidisk format detection is critical for correct operation:
- If misidentified as standard Acorn DFS, directory bytes will appear corrupted
- Deleted files may show directory character as 0x7F instead of proper value
- Start sector interpretation differs (11-bit vs 10-bit)
- File length calculations will be incorrect without proper bit interpretation
- Always verify byte 2 pattern (& 0xC0 == 0xC0) before assuming Solidisk format

### Opus DDOS (Partitioned Format)

Opus DDOS uses a fundamentally different architecture with partitioning.

**Physical Parameters**
- 18 sectors/track
- 40 or 80 tracks
- Double density
- Track-based allocation (4.5KB per track)

**Partition System**

Each physical disk side divides into up to 8 logical volumes (sub-drives):

- Volume names: 0A, 0B, 0C, 0D, 0E, 0F, 0G, 0H (for drive 0)
- Or: 2A, 2B, 2C, 2D, 2E, 2F, 2G, 2H (for drive 2)
- Each volume limited to 252KB (0x3F0 sectors = 63 tracks)
- This avoids need for >10-bit sector addressing

**Track 0 Layout**

Track 0 reserved for system metadata with specific sector assignments:

```
Sectors 0-1:   Volume A catalog (DFS-style, 2 sectors)
Sectors 2-3:   Volume B catalog
Sectors 4-5:   Volume C catalog
Sectors 6-7:   Volume D catalog
Sectors 8-9:   Volume E catalog
Sectors 10-11: Volume F catalog
Sectors 12-13: Volume G catalog
Sectors 14-15: Volume H catalog
Sector 16:     Disc allocation table
Sector 17:     Unused
Tracks 1-79:   Data storage
```

**Disc Allocation Table (Sector 16)**

```
Offset   Length   Field
------   ------   -----
0x00     1        Format marker
                  0x20 = Standard DDOS (fixed value)
0x01     2        Disk size in sectors (little-endian)
                  Standard 80-track DD: 0x05A0 (1440 sectors)
0x03     1        Sectors per track
                  Standard: 0x12 (18 decimal)
0x04     1        Format indicator
                  0x50 = Standard (though 0xFF also observed)
0x05     3        Reserved/unused
0x08     2        Volume A starting track (little-endian word)
0x0A     2        Volume B starting track (little-endian word)
0x0C     2        Volume C starting track (little-endian word)
0x0E     2        Volume D starting track (little-endian word)
0x10     2        Volume E starting track (little-endian word)
0x12     2        Volume F starting track (little-endian word)
0x14     2        Volume G starting track (little-endian word)
0x16     2        Volume H starting track (little-endian word)
0x18     232      Additional allocation data
```

**Note:** Volume start tracks are stored as **little-endian 16-bit words** (pairs of bytes), not single bytes as in some documentation. This allows for flexible disk geometries including 35-track and 40-track formats.

**Standard 80-Track Double-Density Values**
- Disk size: 0x05A0 (1440 sectors = 80 tracks × 18 sectors)
- Sectors per track: 0x12 (18 decimal)
- Format marker: 0x20 (fixed)
- Format indicator: 0x50 (standard)

**Typical Volume Allocation**

Example configuration for 80-track disk:
- Volume A: Starts at track 1 (bytes 0x08-0x09 = 0x0001)
- Volume B: Starts at track 57 (0x39) (bytes 0x0A-0x0B = 0x0039)
- Volumes C-H: May be undefined/unallocated (0x0000)

This gives Volume A ~252KB (56 tracks × 18 sectors × 256 bytes) and Volume B the remaining space.

**Volume Catalog Structure**

Each volume has a standard DFS-style catalog in 2 sectors:
- Maximum 31 files per volume
- 8 volumes × 31 files = 248 files per side
- Double-sided system: up to 992 files total

**Sector Numbering**

- Sector 0 = first file sector in volume (catalog is outside partition)
- Sector numbers relative to volume start track
- Physical track = allocation_table[volume_start_track] + (sector / 18)

**Format Identification**

Primary identifier: Configuration byte at sector 16, offset 0x00
- Must be 0x00, 0x20, or possibly other Opus-specific values
- NOT a standard DFS catalog structure in sectors 0-1
- Sectors 0-1 contain volume A catalog instead

**Compatibility**

- Completely incompatible with standard Acorn DFS
- BBC Micro sees each volume as separate drive
- Cannot mix Opus and Acorn disks in same system without ROM switching

## MMB Container Format

MMB (Multi-Media Beeb) is a container format that stores multiple disc images in a single file, commonly used with SD card-based storage solutions for BBC Micro.

### Standard MMB Structure

**File Organization**
- First 8KB (32 sectors): MMB catalog and boot configuration
- Remaining space: Individual disc images, each 200KB (204,800 bytes)
- Disc N starts at offset: `N × 204,800 + 8,192`
- Maximum 511 discs in standard MMB (before extension)

**MMB Catalog Structure (First 8KB)**

```
Offset   Length   Content
------   ------   -------
0x0000   8        Boot configuration (startup image names)
0x0008   8        Reserved/unused
0x0010   16       Disc 0 catalog entry
0x0020   16       Disc 1 catalog entry
...
0x1FF0   16       Disc 510 catalog entry
```

**Catalog Entry Format (16 bytes per disc)**

```
Offset   Length   Field
------   ------   -----
0x00     12       Disc name (null-terminated if <12 chars)
0x0C     3        Reserved/unused
0x0F     1        Status byte
```

**Status Byte Values**
- `0x00` (0): Locked (read-only)
- `0x0F` (15): Read/write
- `0xF0` (240): Unformatted
- `0xFF` (255): Invalid/empty slot

**Boot Configuration**
- Bytes 0x0000-0x0007: Names of up to 8 disc images to auto-boot
- Format: 8 consecutive characters
- Unused boot slots: null bytes

### Extended MMB Format

The extended MMB format supports up to 8,176 disc images in a ~1.7GB file through catalog chaining.

**Extension Mechanism**

Uses byte 8 (offset 0x0008) with special values:
```
Byte 8 value: 0xA# where # = 1-15
              Indicates # additional catalog extents
              Each extent adds 511 more disc slots
```

**Extent Calculation**
- Extent 0: Discs 0-510 (standard MMB catalog at offset 0)
- Extent 1: Discs 511-1021 (second catalog at offset 8192)
- Extent 2: Discs 1022-1532 (third catalog at offset 16384)
- ...
- Maximum: 16 extents = 8,176 total discs

**Backwards Compatibility**
- BBC Micro hardware reads only first catalog (discs 0-510)
- Extended catalogs accessible only via PC-based tools
- Byte 8 = 0xA1 to 0xAF signals extended format to compatible software
- Standard tools ignore byte 8, see only first 511 discs

### MMB Implementation Notes

**Disc Image Format Within MMB**
- Each disc slot contains exactly 200KB (204,800 bytes)
- Standard 80-track, 10 sectors/track, single-sided Acorn DFS format
- No support for DDFS, Solidisk, or Opus formats within MMB
- Each disc is independent with its own catalog in sectors 0-1

**Multi-Catalog Operation Restrictions**

Some operations restricted on multi-catalog (Watford 62-file, Solidisk chained) discs:
- Delete: Single catalog only
- Access (lock/unlock): Single catalog only
- Compact: Single catalog only
- Add files: May work but catalog chain management complex
- Read operations: Generally compatible across all formats

**MMB Tools Compatibility**
- Different tools may use different naming conventions
- Status byte interpretation varies between implementations
- Always validate catalog structure before writes
- Backup MMB files before extensive modifications

## Format Detection Algorithm

### Multi-Stage Heuristic Approach

A robust detection algorithm should proceed through multiple stages:

**Stage 1: File Size Analysis**

```
file_size = len(disk_image)

if file_size % 256 != 0:
    return INVALID  # Not a valid sector-based image

sectors_total = file_size // 256

# Calculate possible geometries
possible_formats = []

for sectors_per_track in [10, 16, 18]:
    if sectors_total % sectors_per_track != 0:
        continue

    tracks_total = sectors_total // sectors_per_track

    # Single-sided options
    if tracks_total in [35, 40, 80]:
        possible_formats.append({
            'sides': 1,
            'tracks': tracks_total,
            'sectors_per_track': sectors_per_track
        })

    # Double-sided options
    if tracks_total % 2 == 0:
        tracks_per_side = tracks_total // 2
        if tracks_per_side in [35, 40, 80]:
            possible_formats.append({
                'sides': 2,
                'tracks': tracks_per_side,
                'sectors_per_track': sectors_per_track
            })
```

**Stage 2: Catalog Validation**

For each possible format, attempt to parse catalog:

```
def validate_catalog(disk_image, geometry):
    sector0 = disk_image[0:256]
    sector1 = disk_image[256:512]

    # Extract disk info
    num_files_times_8 = sector1[0x05]
    boot_and_sectors = sector1[0x06]
    sectors_low = sector1[0x07]

    # Basic validation
    if num_files_times_8 % 8 != 0:
        return False
    if num_files_times_8 > 248:
        return False
    if (boot_and_sectors & 0xC0) != 0:  # Reserved bits
        return False

    # Reconstruct sector count
    sector_count = sectors_low | ((boot_and_sectors & 0x03) << 8)
    if geometry['sectors_per_track'] >= 16:
        # May use bit 2 for 11-bit addressing
        sector_count |= ((boot_and_sectors & 0x04) << 8)

    # Check against geometry
    expected_sectors = geometry['tracks'] * geometry['sides'] * geometry['sectors_per_track']
    if sector_count != expected_sectors:
        return False

    # Validate file entries...
    return True
```

**Stage 3: Format-Specific Markers**

```
def detect_variant(disk_image):
    sector0 = disk_image[0:256]
    sector1 = disk_image[256:512]

    # Check for Opus DDOS (if 18 sectors/track)
    if len(disk_image) >= 18 * 256:
        sector16 = disk_image[16 * 256 : 17 * 256]
        config_byte = sector16[0x00]
        if config_byte in [0x00, 0x20]:
            # Likely Opus DDOS
            return 'OPUS_DDOS'

    # Check for Watford 62-file catalog
    if len(disk_image) >= 4 * 256:
        sector2 = disk_image[2 * 256 : 3 * 256]
        if sector2[0:12] == bytes([0xAA] * 12):
            return 'WATFORD_62FILE'

    # Check byte 0x106 for format hints
    boot_and_sectors = sector1[0x06]
    bit3 = (boot_and_sectors >> 3) & 1
    bit2 = (boot_and_sectors >> 2) & 1

    if bit3 == 0 and bit2 == 1:
        return 'WATFORD_DDFS'  # >256KB WDFS
    elif bit3 == 1:
        return 'HDFS'  # Hierarchical DFS

    # Check for Solidisk chained catalog
    if (sector0[0x02] & 0xC0) == 0xC0:
        return 'SOLIDISK_CHAINED'

    # Default to standard Acorn DFS
    return 'ACORN_DFS'
```

**Stage 4: Confidence Scoring**

Assign confidence levels based on multiple factors:

```
confidence = 0

# Catalog validates: +50
if catalog_valid:
    confidence += 50

# File ordering correct: +20
if files_in_order:
    confidence += 20

# No file overlaps: +20
if no_overlaps:
    confidence += 20

# Format-specific marker found: +10
if variant_marker_found:
    confidence += 10

# Return: (format, confidence)
# confidence >= 90: Very likely correct
# confidence >= 70: Probably correct
# confidence >= 50: Possible, needs verification
# confidence < 50: Unlikely or corrupted
```

### Edge Cases and Limitations

**Ambiguous File Sizes**

The 204,800 byte case requires additional analysis:
1. Parse catalog assuming 80-track SSD
2. Parse catalog assuming 40-track DSD
3. If DSD, check if second side catalog also valid
4. Choose format with higher confidence score

**Corrupted Catalogs**

If catalog fails validation:
- Try alternate interpretations (SSD vs DSD)
- Check for partial corruption (some entries valid)
- Look for secondary catalogs (Watford, Solidisk)
- Consider file size as fallback

**Mixed-Format DSD**

Theoretically possible but extremely rare:
- Side 0: Acorn DFS (10 sectors/track)
- Side 1: Watford DDFS (18 sectors/track)

Detection impossible from file size alone. Would require:
- Custom SectorImage implementation
- Separate catalog parsing per side
- Out of scope for standard detection

**Non-Standard Implementations**

Some variants may exist with:
- Non-standard track counts (35, 42, etc.)
- Proprietary extensions
- Hybrid formats

These require special handling or may be undetectable.

## Implementation Recommendations

### Detection Priority Order

1. **File size validation** (quick rejection of invalid sizes)
2. **Standard Acorn DFS catalog check** (most common)
3. **Opus DDOS detection** (distinctive sector 16 structure)
4. **Watford 62-file detection** (0xAA marker pattern)
5. **Byte 0x106 analysis** (DDFS variants)
6. **Solidisk chaining detection** (byte 2 pattern)
7. **File entry validation** (thorough but slow)

### Confidence Thresholds

For automatic format selection:
- **≥90%**: Proceed with format automatically
- **70-89%**: Warn user, allow override
- **50-69%**: Require user confirmation
- **<50%**: Reject or mark as unknown

### Fallback Strategies

If catalog parsing fails:
1. Report all geometries matching file size
2. Let user select format manually
3. Attempt read-only operations with each format
4. Choose format that produces most valid-looking files

## References and Sources

This document synthesizes information from the following sources:

### Primary Sources

- [stardot.org.uk Acorn 8-bit DFS Disc Formats](https://stardot.org.uk/forums/viewtopic.php?t=11924) - Comprehensive overview of DFS disc formats with links to further references
- [stardot.org.uk DDFS File Format Discussion](https://stardot.org.uk/forums/viewtopic.php?t=20187) - Comprehensive forum thread covering format variants and identification techniques
- [MDFS.net DFS Filesystem Documentation](https://mdfs.net/Docs/Comp/Disk/Format/DFS) - Authoritative byte-level format specifications for Acorn, Watford, Solidisk, and Duggan DFS variants
- [BeebWiki: Acorn DFS Disc Format](https://beebwiki.mdfs.net/Acorn_DFS_disc_format) - Detailed catalog structure and validation heuristics
- [BeebWiki: Opus DDOS](https://beebwiki.mdfs.net/Opus_DDOS) - Technical specifications for Opus DDOS partition system

### Implementation References

- [b-em Emulator: sdf-geo.c](https://github.com/stardot/b-em/blob/master/src/sdf-geo.c) - Practical geometry detection algorithms used in BBC Micro emulator
- [MMB_Utils README](https://github.com/sweharris/MMB_Utils/blob/master/README) - Format specifications for Multi-Media Beeb images
- [MMB Utils Technical Documentation](https://sweh.spuddy.org/Beeb/mmb_utils.html) - Comprehensive MMB container format specification, Opus DDOS allocation table details, and Solidisk format identification notes
- [Watford DFS Manual](https://acorn.huininga.nl/pub/unsorted/manuals/Watford%20DFS-Manual/WE_DFS_manual.html) - Official documentation for Watford Electronics DFS features and 62-file catalog

### Additional Resources

- [Wikipedia: Disc Filing System](https://en.wikipedia.org/wiki/Disc_Filing_System) - Historical context and overview of DFS variants
- [BBC Micro Disk Controllers](http://www.adsb.co.uk/bbc/disk_controllers/) - Hardware differences between Acorn 8271 and WD1770-based systems
- [stardot.org.uk: Solidisk DDFS Data Retrieval](https://stardot.org.uk/forums/viewtopic.php?t=22393) - Practical discussion of Solidisk format compatibility issues

## Appendix A: Byte Offset Quick Reference

### Disk Catalog (Sector 1)

| Offset | Field | Bits | Description |
|--------|-------|------|-------------|
| 0x000-0x003 | Disk title (part 2) | - | Last 4 chars of 12-char title |
| 0x004 | Cycle number | - | BCD boot count |
| 0x005 | File count × 8 | - | Number of files × 8 (max 248) |
| 0x006 | Boot/sectors | 7-6 | Reserved (0) |
| | | 5-4 | Boot option |
| | | 3 | DFS type (0=DFS, 1=HDFS) |
| | | 2 | Sector count b10 |
| | | 1-0 | Sector count b9-8 |
| 0x007 | Sector count | 7-0 | Sector count b7-0 |

### File Entry (Sector 1, offset 0x08 + n×8)

| Offset | Field | Description |
|--------|-------|-------------|
| +0 | Load address low | Bits 7-0 |
| +1 | Load address | Bits 15-8 |
| +2 | Exec address low | Bits 7-0 |
| +3 | Exec address | Bits 15-8 |
| +4 | Length low | Bits 7-0 |
| +5 | Length high | Bits 15-8 |
| +6 | Extended bits | See byte 0x106 structure |
| +7 | Start sector | Bits 7-0 |

## Appendix B: Format Detection Decision Tree

```
START
  │
  ├─ File size % 256 ≠ 0? → INVALID
  │
  ├─ Calculate sectors_per_track possibilities (10, 16, 18)
  │
  ├─ For each geometry:
  │    │
  │    ├─ Read sector 1, byte 0x06 (boot_and_sectors)
  │    ├─ Read sector 1, byte 0x07 (sectors_low)
  │    ├─ Reconstruct sector count (10 or 11 bits)
  │    ├─ Does sector count match geometry?
  │    │     NO → Try next geometry
  │    │     YES ↓
  │    │
  │    ├─ Validate catalog structure
  │    │     INVALID → Try next geometry
  │    │     VALID ↓
  │    │
  │    ├─ Check format-specific markers:
  │    │    │
  │    │    ├─ Sector 16 byte 0 = 0x00 or 0x20? → OPUS DDOS
  │    │    ├─ Sector 2 bytes 0-11 = 0xAA × 12? → WATFORD 62-FILE
  │    │    ├─ Sector 0 byte 2 & 0xC0 = 0xC0? → SOLIDISK CHAINED
  │    │    ├─ Byte 0x06 bit 3=0, bit 2=1? → WATFORD DDFS
  │    │    ├─ Byte 0x06 bit 3=1? → HDFS
  │    │    └─ sectors_per_track = 16? → SOLIDISK DDFS
  │    │         sectors_per_track = 10? → ACORN DFS
  │    │
  │    └─ Score confidence, record result
  │
  └─ Return highest-confidence format
```

---

**Document Version**: 1.1
**Last Updated**: December 2024
**Maintained by**: oaknut-dfs project

**Version History**:
- 1.1 (Dec 2024): Added MMB container format, DSD concatenation mode, extended Opus DDOS allocation table details, Solidisk detection issues and deleted file handling
- 1.0 (Dec 2024): Initial comprehensive documentation of BBC Micro disc formats

# Acorn DFS Disk Image Format Specification

This document describes the SSD (Single-Sided Disk) and DSD (Double-Sided Disk) image formats used by Acorn DFS (Disc Filing System) on the BBC Micro.

## Overview

Acorn DFS disk images are raw sector dumps with no metadata headers. Format detection relies on file extensions (.ssd, .dsd) and geometric properties.

### Key Characteristics

- **Sector size:** 256 bytes (fixed)
- **Sectors per track:** 10 (fixed)
- **Track size:** 2,560 bytes (10 × 256)
- **No metadata header:** Images start directly with sector 0 data
- **Single density FM encoding** (historical; images contain only data, no encoding)

## Disk Geometry

### SSD (Single-Sided Disk)

- **Tracks:** 40 or 80
- **Total sectors:** 400 (40-track) or 800 (80-track)
- **Image size:** 102,400 bytes (40-track) or 204,800 bytes (80-track)
- **Layout:** Sequential sectors (0, 1, 2, ..., N)

```
Physical layout:
Track 0: Sectors 0-9    (bytes 0-2559)
Track 1: Sectors 10-19  (bytes 2560-5119)
Track 2: Sectors 20-29  (bytes 5120-7679)
...
```

### DSD (Double-Sided Disk)

- **Tracks:** 40 or 80 per side
- **Total sectors:** 800 (40-track) or 1,600 (80-track)
- **Image size:** 204,800 bytes (40-track) or 409,600 bytes (80-track)

#### DSD Layout Variants

**Interleaved format (standard):**
Tracks alternate between sides throughout the image.

```
Physical layout:
Side 0 Track 0: Sectors 0-9     (bytes 0-2559)
Side 1 Track 0: Sectors 10-19   (bytes 2560-5119)
Side 0 Track 1: Sectors 20-29   (bytes 5120-7679)
Side 1 Track 1: Sectors 30-39   (bytes 7680-10239)
...
```

**Sequential format (less common):**
All tracks from side 0, then all tracks from side 1.

```
Physical layout:
Side 0 Track 0: Sectors 0-9
Side 0 Track 1: Sectors 10-19
...
Side 0 Track 39: Sectors 390-399
Side 1 Track 0: Sectors 400-409
Side 1 Track 1: Sectors 410-419
...
```

## Catalog Structure

The catalog occupies **sectors 0 and 1** (first two sectors of track 0, 512 bytes total).

### Sector 0 (Bytes 0x00-0xFF)

| Offset | Length | Description |
|--------|--------|-------------|
| 0x00   | 8      | Disk title (first 8 characters, ASCII, space-padded) |
| 0x08   | 8      | File 0 entry (name + directory byte) |
| 0x10   | 8      | File 1 entry (name + directory byte) |
| ...    | ...    | Additional file entries (up to 31 files) |
| 0xF8   | 8      | File 30 entry (last possible file) |

**File entry in Sector 0 (8 bytes):**

| Offset | Length | Description |
|--------|--------|-------------|
| +0     | 7      | Filename (ASCII, space-padded, max 7 chars) |
| +7     | 1      | Directory byte (bit 7: locked flag, bits 0-6: directory character) |

### Sector 1 (Bytes 0x100-0x1FF)

| Offset | Length | Description |
|--------|--------|-------------|
| 0x00   | 4      | Disk title (last 4 characters) |
| 0x04   | 1      | Cycle number (incremented on catalog changes) |
| 0x05   | 1      | Last entry pointer (number_of_files × 8) |
| 0x06   | 1      | Extra byte (bits 0-1: high bits of total sectors, bits 4-5: boot option) |
| 0x07   | 1      | Total sectors (low 8 bits) |
| 0x08   | 8      | File 0 metadata |
| 0x10   | 8      | File 1 metadata |
| ...    | ...    | Additional file metadata |
| 0xF8   | 8      | File 30 metadata (last possible file) |

**File metadata in Sector 1 (8 bytes):**

| Offset | Length | Description |
|--------|--------|-------------|
| +0     | 2      | Load address (low 16 bits, little-endian) |
| +2     | 2      | Execution address (low 16 bits, little-endian) |
| +4     | 2      | File length (low 16 bits, little-endian) |
| +6     | 1      | Extra byte (high bits of addresses/length/sector) |
| +7     | 1      | Start sector (low 8 bits) |

**Extra byte bit layout (offset +6):**

| Bits | Description |
|------|-------------|
| 0-1  | High 2 bits of start sector (forms 10-bit sector number) |
| 2-3  | High 2 bits of load address (bits 16-17 of 18-bit address) |
| 4-5  | High 2 bits of file length (bits 16-17 of 18-bit value) |
| 6-7  | High 2 bits of execution address (bits 16-17 of 18-bit address) |

### Reconstructing Multi-Byte Values

**Load Address (18-bit → 32-bit with sign extension):**
```python
load_low = read_word_le(offset + 0)
extra = read_byte(offset + 6)
load_addr = load_low | ((extra & 0x0C) << 14)

# Sign extension for I/O processor addresses (0xFFFFxxxx range)
if load_addr & 0x30000 == 0x30000:
    load_addr |= 0xFFFC0000
```

**Execution Address (18-bit → 32-bit with sign extension):**
```python
exec_low = read_word_le(offset + 2)
extra = read_byte(offset + 6)
exec_addr = exec_low | ((extra & 0xC0) << 10)

# Sign extension
if exec_addr & 0x30000 == 0x30000:
    exec_addr |= 0xFFFC0000
```

**File Length (18-bit):**
```python
length_low = read_word_le(offset + 4)
extra = read_byte(offset + 6)
length = length_low | ((extra & 0x30) << 12)
# Maximum: 262,144 bytes (0x40000)
```

**Start Sector (10-bit):**
```python
sector_low = read_byte(offset + 7)
extra = read_byte(offset + 6)
start_sector = sector_low | ((extra & 0x03) << 8)
# Maximum: 1,023 sectors
```

**Total Sectors (10-bit):**
```python
sectors_low = read_byte(0x107)
extra = read_byte(0x106)
total_sectors = sectors_low | ((extra & 0x03) << 8)
```

**Boot Option (2-bit):**
```python
extra = read_byte(0x106)
boot_option = (extra >> 4) & 0x03
# 0: None (*OPT 4,0)
# 1: *LOAD $.!BOOT (*OPT 4,1)
# 2: *RUN $.!BOOT (*OPT 4,2)
# 3: *EXEC $.!BOOT (*OPT 4,3)
```

## File Storage

### File Data Layout

Files are stored contiguously starting from their designated start sector. Each file occupies `ceil(file_length / 256)` sectors.

```
Sector 0:     Catalog sector 0
Sector 1:     Catalog sector 1
Sector 2+:    File data area
```

**Example:**
- File "HELLO" starts at sector 2, length 384 bytes → occupies sectors 2, 3 (2 sectors)
- File "DATA" starts at sector 4, length 100 bytes → occupies sector 4 (1 sector)

### Physical Address Calculation

**SSD (sequential layout):**
```python
physical_offset = sector_number * 256
```

**DSD (interleaved layout):**
```python
track = sector_number // 10
sector_in_track = sector_number % 10
side = track % 2
physical_track = track // 2

physical_offset = (
    physical_track * 2560 * 2 +  # Skip complete track pairs
    side * 2560 +                 # Offset to correct side
    sector_in_track * 256         # Offset within track
)
```

**DSD (sequential layout):**
```python
physical_offset = sector_number * 256
```

## File Attributes

### Directory Character

The directory byte (bits 0-6) stores a single ASCII character representing the directory:
- `$` - Root directory (default)
- `A-Z` - Named directories

Full filename format: `{directory}.{filename}` (e.g., `$.HELLO`, `A.DATA`)

### Locked Flag

Bit 7 of the directory byte indicates if a file is locked:
- `0` - Unlocked (can be deleted/modified)
- `1` - Locked (protected from deletion/modification)

### Load and Execution Addresses

- **Load address:** Memory location where file should be loaded
- **Execution address:** Entry point for machine code execution (used by `*RUN`)

Special case: Load address `0xFFFFxxxx` indicates RISC OS filetype encoding (not common in DFS).

## Catalog Limits

- **Maximum files:** 31
- **Maximum filename length:** 7 characters (excluding directory prefix)
- **Disk title length:** 12 characters
- **Maximum file size:** 262,144 bytes (0x40000, 18-bit)
- **Maximum sectors:** 1,023 (10-bit, though practical limit is lower)

## Common Disk Sizes

| Type | Tracks | Sides | Sectors | Size (bytes) | Size (KB) |
|------|--------|-------|---------|--------------|-----------|
| SSD  | 40     | 1     | 400     | 102,400      | 100       |
| SSD  | 80     | 1     | 800     | 204,800      | 200       |
| DSD  | 40     | 2     | 800     | 204,800      | 200       |
| DSD  | 80     | 2     | 1,600   | 409,600      | 400       |

## Format Detection

Since SSD/DSD files lack magic numbers or headers:

1. **File extension:** `.ssd` or `.dsd`
2. **File size:** Must be multiple of 2,560 (one track)
3. **Catalog validation:**
   - Last entry pointer ≤ 248 (31 files × 8 bytes)
   - Total sectors matches image size
   - Filenames contain valid ASCII characters

## References

- Acorn *Advanced Disk User Guide For The BBC Microcomputer* by Colin Pharo
- [Jonathan Harston's DFS Documentation](https://mdfs.net/Docs/Comp/Disk/Format/DFS)
- [stardot.org.uk DFS Format Discussion](https://stardot.org.uk/forums/viewtopic.php?t=24533)
- [stardot.org.uk Acorn 8-bit DFS Disc Formats](https://stardot.org.uk/forums/viewtopic.php?t=11924) — comprehensive overview of DFS disc formats with links to further references
- Reference implementations: beebasm, b-em, BeebEm

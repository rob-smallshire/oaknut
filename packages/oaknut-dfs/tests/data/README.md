# Test Data for oaknut-dfs

This directory contains test data generators and reference disk images for validating oaknut-dfs against real BBC Micro DFS implementations.

## Directory Structure

```
tests/data/
├── generators/          BBC BASIC programs to create test disks
│   ├── 01-basic-validation.bas
│   ├── 02-edge-cases.bas
│   ├── 03-fragmented.bas
│   └── 04-double-sided.bas
├── images/             Reference disk images created by generators
│   ├── 01-basic-validation.ssd
│   ├── 02-edge-cases.ssd
│   ├── 03-fragmented.ssd
│   └── 04-double-sided.dsd
└── README.md           This file
```

## Generating Test Images

### Prerequisites

- BBC Micro emulator (b2 recommended, or BeebEm)
- oaknut-dfs installed for creating blank disks

### Process

Each `.bas` file in `generators/` creates a specific test scenario. The file header specifies:
- Target format (SSD or DSD)
- Track count (40T or 80T)
- Expected output filename

#### Step 1: Create Blank Disk (if needed)

For 40T disks, create using oaknut-dfs (b2 doesn't support 40T creation):

```bash
oaknut-dfs create tests/data/images/01-basic-validation.ssd --tracks=40
```

For 80T disks, you can create in b2 or using oaknut-dfs:

```bash
oaknut-dfs create tests/data/images/01-basic-validation.ssd --tracks=80
oaknut-dfs create tests/data/images/04-double-sided.dsd --tracks=80 --double-sided
```

#### Step 2: Run Generator in Emulator

1. Open the blank disk in b2
2. Load the BBC BASIC program:
   - Paste the entire `.bas` file content into b2
   - Or use `*EXEC` if you've copied it onto the disk

3. Run the program:
   ```
   RUN
   ```

4. The program will create all test files and report progress
5. Verify with `*CAT`

#### Step 3: Export Disk Image

Save the disk from the emulator to the `images/` directory with the exact filename specified in the generator comments.

## Test Scenarios

### 01-basic-validation.ssd (80T SSD)

**Purpose:** Basic functionality validation

**Contents:**
- 12 files across 3 directories ($, A, B)
- Text files with known content
- Binary file with sequential data (0-255)
- Various filename lengths (1-7 chars)
- One locked file
- Specific load/exec addresses

**Tests:**
- File reading
- Metadata preservation
- Directory handling
- Lock status

### 02-edge-cases.ssd (80T SSD)

**Purpose:** Boundary conditions and edge cases

**Contents:**
- Exactly 31 files (catalog full)
- All 7-character filenames
- Special characters (!BOOT, TEST-1, FILE_31)
- I/O processor address testing (0xFFFFxxxx)

**Tests:**
- Catalog full detection
- Special character handling
- Maximum filename length
- High-bit address preservation

### 03-fragmented.ssd (80T SSD)

**Purpose:** Fragmentation handling

**Strategy:**
1. Create files A, B, C, D, E
2. Delete B and D
3. Result: A [3-sector gap] C [4-sector gap] E

**Contents:**
- Files with known sizes (2, 3, 4 sectors)
- Intentional gaps from deleted files
- Marker file after gaps

**Tests:**
- Gap detection
- Free space calculation
- Sector allocation
- Compact operation

### 04-double-sided.dsd (80T DSD)

**Purpose:** Double-sided disk with separate catalogs per side

**Important:** DFS treats double-sided disks as **two separate drives**:
- `*DRIVE 0` = Side 0 (first side) - 400 sectors
- `*DRIVE 2` = Side 1 (second side) - 400 sectors
- Each side has its own independent catalog
- Total capacity: 800 sectors across both sides

**Contents:**

*Side 0 (Drive 0):*
- 5 small files (1 sector each)
- 3 medium files (10 sectors each)
- 5 files in directory A
- Total: 13 files

*Side 1 (Drive 2):*
- 3 large files (20 sectors each)
- 1 very large file (50 sectors)
- 5 files in directory B
- Total: 9 files

**Tests:**
- Drive switching between sides
- Independent catalogs per side
- Track interleaving physical offsets
- Files spanning tracks on each side
- Proper capacity detection (400 sectors per side)

## Using Test Images in Tests

Example test structure:

```python
import pytest
from pathlib import Path
from oaknut_dfs.dfs_filesystem import DFSImage

TEST_DATA_DIR = Path(__file__).parent / "data" / "images"

def test_basic_validation_disk():
    """Test against reference disk created in b2."""
    disk_path = TEST_DATA_DIR / "01-basic-validation.ssd"

    with DFSImage.open(disk_path) as disk:
        # Verify expected files exist
        assert disk.exists("$.TEXT")
        assert disk.exists("$.BINARY")
        assert disk.exists("$.LOCKED")

        # Verify content
        text_data = disk.load("$.TEXT")
        assert b"Simple text content" in text_data

        # Verify binary data (0-255 sequence)
        binary_data = disk.load("$.BINARY")
        assert len(binary_data) == 256
        assert list(binary_data) == list(range(256))

        # Verify metadata
        info = disk.get_file_info("$.BINARY")
        assert info.load_address == 0x2000
        assert info.exec_address == 0x2000

        # Verify locked status
        info = disk.get_file_info("$.LOCKED")
        assert info.locked is True
```

## Maintenance

When updating test generators:

1. Update the `.bas` file with changes
2. Re-run in emulator to regenerate image
3. Commit both `.bas` and `.ssd`/`.dsd` files
4. Update this README if test scenario changes

## Notes

### BBC BASIC File Path Limitations

**Important:** BBC BASIC's `OPENOUT` command cannot accept directory-qualified filenames. This is a critical constraint for the generator programs:

**Does NOT work:**
```basic
file%=OPENOUT("A.DATA1")  ' ERROR: Cannot use directory prefix with OPENOUT
```

**Correct approach:**
```basic
*DIR A                    ' Change to directory A
file%=OPENOUT("DATA1")    ' Create file with simple name
CLOSE#file%
*DIR $                    ' Return to root directory
```

**Exception for star commands:** Star commands like `*DELETE`, `*ACCESS`, and `*RENAME` DO accept qualified filenames:
```basic
*DELETE $.TEMP            ' This works fine
*ACCESS $.LOCKED L        ' This works fine
```

All generator programs have been updated to follow this pattern. When creating files in directories other than $, they:
1. Use `*DIR` to change to the target directory
2. Create files with simple filenames
3. Return to `$` with `*DIR $`

### Other Notes

- **Double-sided disks (DSD)**: DFS treats these as TWO SEPARATE SIDES, not one unified disk:
  - Side 0: Sectors 0-399 (BBC DFS `*DRIVE 0`)
  - Side 1: Sectors 0-399 (BBC DFS `*DRIVE 2`)
  - Each side has its own catalog (sectors 0-1 per side)
  - Physical layout uses track interleaving (side 0 track 0, side 1 track 0, side 0 track 1, ...)
  - oaknut-dfs uses `side=0` and `side=1` parameters rather than DFS drive numbers
- **Track interleaving**: DSD files use interleaved track layout at the physical level, but logically each side is accessed independently
- **40T limitations**: b2 may not support creating 40T disks, but can read them if created with oaknut-dfs
- **Emulator compatibility**: Test images should work in any BBC Micro emulator (BeebEm, b2, MAME, etc.)
- **File ordering**: Files are allocated sequentially in sectors, starting at sector 2 (after catalog)

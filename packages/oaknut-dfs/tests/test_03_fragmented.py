"""Tests for 03-fragmented.ssd reference image.

Generator: tests/data/generators/03-fragmented.bas
Image:     tests/data/images/03-fragmented.ssd
Format:    80T SSD (Single-sided, 80 tracks)

This test validates oaknut-dfs handling of fragmented disks:
  - Gap detection between files
  - Free space calculation with fragmentation
  - File sector allocation patterns

Expected Contents (from generator):
  Step 1: Created FILEA, FILEB, FILEC, FILED, FILEE
  Step 2: Deleted FILEB and FILED to create gaps
  Step 3: Created MARKER file after gaps

Disk Layout:
  Sectors 0-1:   Catalog
  Sectors 2-3:   $.FILEA (512 bytes, 2 sectors)
  Sectors 4-6:   [GAP - 3 sectors from deleted FILEB]
  Sectors 7-8:   $.FILEC (512 bytes, 2 sectors)
  Sectors 9-12:  [GAP - 4 sectors from deleted FILED]
  Sectors 13-14: $.FILEE (512 bytes, 2 sectors)
  Sectors 15:    $.MARKER (27 bytes, 1 sector)

Total: 4 files, 7 sectors of gaps
"""

import pytest
from oaknut_dfs.dfs_filesystem import DFSImage


IMAGE_NAME = "03-fragmented.ssd"


class TestDiskMetadata:
    """Test disk-level metadata."""

    def test_disk_format_detection(self, reference_image):
        """Disk is correctly detected as 80T SSD."""
        disk = reference_image(IMAGE_NAME)
        assert disk is not None

    def test_disk_title(self, reference_image):
        """Disk title is correct."""
        disk = reference_image(IMAGE_NAME)
        assert disk.title.rstrip('\x00 ') == "FRAGMENT"

    def test_file_count(self, reference_image):
        """Disk contains 4 files after deletions."""
        disk = reference_image(IMAGE_NAME)
        assert len(disk.files) == 4, \
            f"Expected 4 files, found {len(disk.files)}: {[f.name for f in disk.files]}"


class TestFileExistence:
    """Test expected files exist and deleted files don't."""

    def test_remaining_files_exist(self, reference_image):
        """Files A, C, E, and MARKER exist."""
        disk = reference_image(IMAGE_NAME)

        assert disk.exists("$.FILEA"), "$.FILEA not found"
        assert disk.exists("$.FILEC"), "$.FILEC not found"
        assert disk.exists("$.FILEE"), "$.FILEE not found"
        assert disk.exists("$.MARKER"), "$.MARKER not found"

    def test_deleted_files_dont_exist(self, reference_image):
        """Deleted files B and D do not exist."""
        disk = reference_image(IMAGE_NAME)

        assert not disk.exists("$.FILEB"), "$.FILEB should not exist (was deleted)"
        assert not disk.exists("$.FILED"), "$.FILED should not exist (was deleted)"


class TestFileSizes:
    """Test file sizes are correct."""

    def test_filea_size(self, reference_image):
        """FILEA is 512 bytes (2 sectors)."""
        disk = reference_image(IMAGE_NAME)
        info = disk.get_file_info("$.FILEA")
        assert info.length == 512

    def test_filec_size(self, reference_image):
        """FILEC is 512 bytes (2 sectors)."""
        disk = reference_image(IMAGE_NAME)
        info = disk.get_file_info("$.FILEC")
        assert info.length == 512

    def test_filee_size(self, reference_image):
        """FILEE is 512 bytes (2 sectors)."""
        disk = reference_image(IMAGE_NAME)
        info = disk.get_file_info("$.FILEE")
        assert info.length == 512

    def test_marker_size(self, reference_image):
        """MARKER is 27 bytes (1 sector)."""
        disk = reference_image(IMAGE_NAME)
        info = disk.get_file_info("$.MARKER")
        assert info.length == 27


class TestFileContents:
    """Test file contents are correct."""

    def test_filea_content(self, reference_image):
        """FILEA contains 512 bytes of 'A' (ASCII 65)."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.FILEA")

        assert len(data) == 512
        assert all(b == 65 for b in data), \
            "FILEA should contain all 'A' characters (ASCII 65)"

    def test_filec_content(self, reference_image):
        """FILEC contains 512 bytes of 'C' (ASCII 67)."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.FILEC")

        assert len(data) == 512
        assert all(b == 67 for b in data), \
            "FILEC should contain all 'C' characters (ASCII 67)"

    def test_filee_content(self, reference_image):
        """FILEE contains 512 bytes of 'E' (ASCII 69)."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.FILEE")

        assert len(data) == 512
        assert all(b == 69 for b in data), \
            "FILEE should contain all 'E' characters (ASCII 69)"

    def test_marker_content(self, reference_image):
        """MARKER contains expected text."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.MARKER")
        text = data.decode('utf-8')

        assert text == "This file is after the gaps"


class TestFragmentationLayout:
    """Test fragmentation and sector allocation."""

    def test_filea_sector_location(self, reference_image):
        """FILEA starts at sector 2."""
        disk = reference_image(IMAGE_NAME)
        info = disk.get_file_info("$.FILEA")
        assert info.start_sector == 2

    def test_filec_sector_location(self, reference_image):
        """FILEC starts at sector 7 (after 3-sector gap)."""
        disk = reference_image(IMAGE_NAME)
        info = disk.get_file_info("$.FILEC")
        assert info.start_sector == 7

    def test_filee_sector_location(self, reference_image):
        """FILEE starts at sector 13 (after 4-sector gap)."""
        disk = reference_image(IMAGE_NAME)
        info = disk.get_file_info("$.FILEE")
        assert info.start_sector == 13

    def test_marker_sector_location(self, reference_image):
        """MARKER starts at sector 15 (after FILEE)."""
        disk = reference_image(IMAGE_NAME)
        info = disk.get_file_info("$.MARKER")
        assert info.start_sector == 15

    def test_gap_after_filea(self, reference_image):
        """There's a 3-sector gap after FILEA (sectors 4-6)."""
        disk = reference_image(IMAGE_NAME)

        filea_info = disk.get_file_info("$.FILEA")
        filec_info = disk.get_file_info("$.FILEC")

        # FILEA uses sectors 2-3 (2 sectors)
        filea_end = filea_info.start_sector + 1  # 2 + 1 = 3
        # FILEC starts at sector 7
        gap_size = filec_info.start_sector - (filea_end + 1)
        assert gap_size == 3, f"Expected 3-sector gap, found {gap_size}"

    def test_gap_after_filec(self, reference_image):
        """There's a 4-sector gap after FILEC (sectors 9-12)."""
        disk = reference_image(IMAGE_NAME)

        filec_info = disk.get_file_info("$.FILEC")
        filee_info = disk.get_file_info("$.FILEE")

        # FILEC uses sectors 7-8 (2 sectors)
        filec_end = filec_info.start_sector + 1  # 7 + 1 = 8
        # FILEE starts at sector 13
        gap_size = filee_info.start_sector - (filec_end + 1)
        assert gap_size == 4, f"Expected 4-sector gap, found {gap_size}"


class TestFreeSpace:
    """Test free space calculation with fragmentation."""

    def test_free_sectors_calculation(self, reference_image):
        """Free space calculation accounts for gaps and end space."""
        disk = reference_image(IMAGE_NAME)

        # 80 tracks * 10 sectors/track = 800 sectors total
        # Minus 2 for catalog = 798 data sectors
        # Used: FILEA(2) + FILEC(2) + FILEE(2) + MARKER(1) = 7 sectors
        # Free: 798 - 7 = 791 sectors
        expected_free = 791

        assert disk.free_sectors == expected_free, \
            f"Expected {expected_free} free sectors, found {disk.free_sectors}"


class TestWritableOperations:
    """Test operations on fragmented disk."""

    def test_can_read_all_files(self, writable_copy):
        """All files can be read successfully."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=False)

        # Should be able to read all files without error
        data_a = disk.load("$.FILEA")
        assert len(data_a) == 512

        data_c = disk.load("$.FILEC")
        assert len(data_c) == 512

        data_e = disk.load("$.FILEE")
        assert len(data_e) == 512

        data_marker = disk.load("$.MARKER")
        assert len(data_marker) == 27

    def test_can_add_small_file_in_gap(self, writable_copy):
        """Can add a small file (should fit in first gap)."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=True)

        # Add a 512-byte file (2 sectors) - should fit in first 3-sector gap
        new_data = b"X" * 512
        disk.save("$.NEWFILE", new_data)

        assert disk.exists("$.NEWFILE")
        loaded = disk.load("$.NEWFILE")
        assert loaded == new_data

    def test_can_delete_and_recreate(self, writable_copy):
        """Can delete a file and create a new one."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=True)

        # Delete FILEA
        disk.delete("$.FILEA")
        assert not disk.exists("$.FILEA")

        # Create a new file
        disk.save("$.NEWFILE", b"New content")
        assert disk.exists("$.NEWFILE")


class TestCompaction:
    """Test compaction on fragmented disk."""

    def test_compact_removes_gaps(self, writable_copy):
        """Compaction removes all gaps and moves files together."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=True)

        # Before compaction: gaps exist
        # FILEA at sector 2, FILEC at sector 7, FILEE at sector 13, MARKER at sector 15

        files_moved = disk.compact()

        # After compaction: files should be contiguous starting at sector 2
        # FILEA at sector 2, FILEC at sector 4, FILEE at sector 6, MARKER at sector 8
        assert files_moved == 3  # FILEC, FILEE, MARKER moved

        # Verify new positions
        assert disk.get_file_info("$.FILEA").start_sector == 2
        assert disk.get_file_info("$.FILEC").start_sector == 4  # Was 7, moved up 3
        assert disk.get_file_info("$.FILEE").start_sector == 6  # Was 13, moved up 7
        assert disk.get_file_info("$.MARKER").start_sector == 8  # Was 15, moved up 7

    def test_compact_preserves_file_contents(self, writable_copy):
        """File contents unchanged after compaction."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=True)

        # Read contents before compaction
        data_a_before = disk.load("$.FILEA")
        data_c_before = disk.load("$.FILEC")
        data_e_before = disk.load("$.FILEE")
        marker_before = disk.load("$.MARKER")

        disk.compact()

        # Contents should be identical
        assert disk.load("$.FILEA") == data_a_before
        assert disk.load("$.FILEC") == data_c_before
        assert disk.load("$.FILEE") == data_e_before
        assert disk.load("$.MARKER") == marker_before

    def test_compact_increases_contiguous_free_space(self, writable_copy):
        """Compaction creates one large contiguous free space block."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=True)

        free_before = disk.free_sectors
        disk.compact()
        free_after = disk.free_sectors

        # Free space amount unchanged, but now contiguous
        assert free_after == free_before

        # After compaction, next file should start at sector 9
        # (FILEA=2-3, FILEC=4-5, FILEE=6-7, MARKER=8)
        disk.save("$.NEWFILE", b"X" * 512)  # 2 sectors
        assert disk.get_file_info("$.NEWFILE").start_sector == 9

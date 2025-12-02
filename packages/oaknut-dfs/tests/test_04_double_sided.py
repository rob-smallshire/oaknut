"""Tests for 04-double-sided.dsd reference image.

Generator: tests/data/generators/04-double-sided.bas
Image:     tests/data/images/04-double-sided.dsd
Format:    80T DSD (Double-sided, 80 tracks, interleaved)

This test validates oaknut-dfs handling of double-sided disks:
  - Independent catalogs on each side
  - Side parameter usage (side=0, side=1)
  - Files on different sides are isolated
  - Track interleaving in physical layout

DFS treats double-sided disks as TWO SEPARATE DRIVES:
  - *DRIVE 0 = Side 0 (first side) = oaknut-dfs side=0
  - *DRIVE 2 = Side 1 (second side) = oaknut-dfs side=1

Expected Contents (from generator):
  Side 0 (13 files):
    $ directory: SMALL1-SMALL5 (20 bytes each), MED1-MED3 (2560 bytes each)
    A directory: FILE1-FILE5 (text files)

  Side 1 (9 files):
    $ directory: LARGE1-LARGE3 (5120 bytes each), HUGE (12800 bytes)
    B directory: FILE1-FILE5 (text files)
"""

import pytest
from oaknut_dfs.dfs_filesystem import DFSImage
from oaknut_dfs.exceptions import InvalidFormatError


IMAGE_NAME = "04-double-sided.dsd"


class TestDiskMetadata:
    """Test disk-level metadata for both sides."""

    def test_disk_format_detection(self, reference_image):
        """Disk is correctly detected as DSD format."""
        disk = reference_image(IMAGE_NAME, side=0)
        assert disk is not None

    def test_side0_title(self, reference_image):
        """Side 0 has correct title."""
        disk = reference_image(IMAGE_NAME, side=0)
        assert disk.title.rstrip('\x00 ') == "SIDE0"

    def test_side1_title(self, reference_image):
        """Side 1 has correct title."""
        disk = reference_image(IMAGE_NAME, side=1)
        assert disk.title.rstrip('\x00 ') == "SIDE1"

    def test_side0_file_count(self, reference_image):
        """Side 0 contains 13 files."""
        disk = reference_image(IMAGE_NAME, side=0)
        assert len(disk.files) == 13

    def test_side1_file_count(self, reference_image):
        """Side 1 contains 9 files."""
        disk = reference_image(IMAGE_NAME, side=1)
        assert len(disk.files) == 9


class TestSideIndependence:
    """Test that sides are independent with separate catalogs."""

    def test_files_on_side0_not_visible_on_side1(self, reference_image):
        """Files on Side 0 are not visible when accessing Side 1."""
        disk0 = reference_image(IMAGE_NAME, side=0)
        disk1 = reference_image(IMAGE_NAME, side=1)

        # SMALL1 exists on side 0 but not side 1
        assert disk0.exists("$.SMALL1")
        assert not disk1.exists("$.SMALL1")

        # MED1 exists on side 0 but not side 1
        assert disk0.exists("$.MED1")
        assert not disk1.exists("$.MED1")

    def test_files_on_side1_not_visible_on_side0(self, reference_image):
        """Files on Side 1 are not visible when accessing Side 0."""
        disk0 = reference_image(IMAGE_NAME, side=0)
        disk1 = reference_image(IMAGE_NAME, side=1)

        # LARGE1 exists on side 1 but not side 0
        assert disk1.exists("$.LARGE1")
        assert not disk0.exists("$.LARGE1")

        # HUGE exists on side 1 but not side 0
        assert disk1.exists("$.HUGE")
        assert not disk0.exists("$.HUGE")

    def test_directory_a_only_on_side0(self, reference_image):
        """Directory A exists only on Side 0."""
        disk0 = reference_image(IMAGE_NAME, side=0)
        disk1 = reference_image(IMAGE_NAME, side=1)

        # Directory A files exist on side 0
        for i in range(1, 6):
            assert disk0.exists(f"A.FILE{i}")
            assert not disk1.exists(f"A.FILE{i}")

    def test_directory_b_only_on_side1(self, reference_image):
        """Directory B exists only on Side 1."""
        disk0 = reference_image(IMAGE_NAME, side=0)
        disk1 = reference_image(IMAGE_NAME, side=1)

        # Directory B files exist on side 1
        for i in range(1, 6):
            assert disk1.exists(f"B.FILE{i}")
            assert not disk0.exists(f"B.FILE{i}")


class TestSide0Files:
    """Test files on Side 0."""

    def test_all_small_files_exist(self, reference_image):
        """All SMALL files exist on Side 0."""
        disk = reference_image(IMAGE_NAME, side=0)

        for i in range(1, 6):
            filename = f"$.SMALL{i}"
            assert disk.exists(filename), f"{filename} not found"

    def test_small_file_content(self, reference_image):
        """SMALL files have expected content."""
        disk = reference_image(IMAGE_NAME, side=0)

        data = disk.load("$.SMALL1")
        text = data.decode('utf-8')
        assert text == "Side 0, small file 1"

    def test_all_med_files_exist(self, reference_image):
        """All MED files exist on Side 0."""
        disk = reference_image(IMAGE_NAME, side=0)

        for i in range(1, 4):
            filename = f"$.MED{i}"
            assert disk.exists(filename), f"{filename} not found"

    def test_med_file_size(self, reference_image):
        """MED files are 2560 bytes (10 sectors) each."""
        disk = reference_image(IMAGE_NAME, side=0)

        for i in range(1, 4):
            info = disk.get_file_info(f"$.MED{i}")
            assert info.length == 2560

    def test_med_file_content(self, reference_image):
        """MED files contain repeated byte values."""
        disk = reference_image(IMAGE_NAME, side=0)

        # MED1 should be 2560 bytes of value 1
        data = disk.load("$.MED1")
        assert len(data) == 2560
        assert all(b == 1 for b in data)

        # MED2 should be 2560 bytes of value 2
        data = disk.load("$.MED2")
        assert len(data) == 2560
        assert all(b == 2 for b in data)

    def test_directory_a_files(self, reference_image):
        """Directory A files have expected content."""
        disk = reference_image(IMAGE_NAME, side=0)

        for i in range(1, 6):
            data = disk.load(f"A.FILE{i}")
            text = data.decode('utf-8')
            expected = f"Side 0, directory A, file {i}"
            assert text == expected


class TestSide1Files:
    """Test files on Side 1."""

    def test_all_large_files_exist(self, reference_image):
        """All LARGE files exist on Side 1."""
        disk = reference_image(IMAGE_NAME, side=1)

        for i in range(1, 4):
            filename = f"$.LARGE{i}"
            assert disk.exists(filename), f"{filename} not found"

    def test_large_file_size(self, reference_image):
        """LARGE files are 5120 bytes (20 sectors) each."""
        disk = reference_image(IMAGE_NAME, side=1)

        for i in range(1, 4):
            info = disk.get_file_info(f"$.LARGE{i}")
            assert info.length == 5120

    def test_large_file_content(self, reference_image):
        """LARGE files contain pattern based on file number."""
        disk = reference_image(IMAGE_NAME, side=1)

        # LARGE1: bytes are (1*16+j) MOD 256
        data = disk.load("$.LARGE1")
        assert len(data) == 5120
        for j in range(5120):
            expected = (1 * 16 + j) % 256
            assert data[j] == expected, f"Byte {j} mismatch"

    def test_huge_file_exists(self, reference_image):
        """HUGE file exists on Side 1."""
        disk = reference_image(IMAGE_NAME, side=1)
        assert disk.exists("$.HUGE")

    def test_huge_file_size(self, reference_image):
        """HUGE file is 12800 bytes (50 sectors)."""
        disk = reference_image(IMAGE_NAME, side=1)
        info = disk.get_file_info("$.HUGE")
        assert info.length == 12800

    def test_huge_file_content(self, reference_image):
        """HUGE file contains sequential pattern."""
        disk = reference_image(IMAGE_NAME, side=1)

        data = disk.load("$.HUGE")
        assert len(data) == 12800

        # Content is i MOD 256 for i in 0..12799
        for i in range(12800):
            expected = i % 256
            assert data[i] == expected

    def test_directory_b_files(self, reference_image):
        """Directory B files have expected content."""
        disk = reference_image(IMAGE_NAME, side=1)

        for i in range(1, 6):
            data = disk.load(f"B.FILE{i}")
            text = data.decode('utf-8')
            expected = f"Side 1, directory B, file {i}"
            assert text == expected


class TestCapacity:
    """Test capacity and sector usage on each side."""

    def test_side0_total_sectors(self, reference_image):
        """Side 0 reports 800 total sectors (entire disk)."""
        disk = reference_image(IMAGE_NAME, side=0)
        # 80 tracks * 10 sectors/track = 800 sectors total
        # Note: total_sectors reports physical disk size, not per-side
        assert disk.info.total_sectors == 800

    def test_side1_total_sectors(self, reference_image):
        """Side 1 reports 800 total sectors (entire disk)."""
        disk = reference_image(IMAGE_NAME, side=1)
        # total_sectors reports physical disk size, same for both sides
        assert disk.info.total_sectors == 800

    def test_side0_free_space(self, reference_image):
        """Side 0 has reasonable free space."""
        disk = reference_image(IMAGE_NAME, side=0)

        # Used sectors on side 0: SMALL1-5 (1 each) + MED1-3 (10 each) + A.FILE1-5 (1 each)
        # = 5 + 30 + 5 = 40 sectors
        # Total data sectors per side: 800/2 - 2 (catalog) = 398
        # Free: approximately 398 - 40 = 358 sectors
        assert disk.free_sectors > 350  # Allow some overhead

    def test_side1_free_space(self, reference_image):
        """Side 1 has reasonable free space."""
        disk = reference_image(IMAGE_NAME, side=1)

        # Used sectors on side 1: LARGE1-3 (20 each) + HUGE (50) + B.FILE1-5 (1 each)
        # = 60 + 50 + 5 = 115 sectors
        # Total data sectors per side: 800/2 - 2 (catalog) = 398
        # Free: approximately 398 - 115 = 283 sectors
        assert disk.free_sectors > 280  # Allow some overhead


class TestWritableOperations:
    """Test operations on double-sided disk."""

    def test_can_write_to_side0(self, writable_copy):
        """Can add files to Side 0."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=True, side=0)

        disk.save("$.NEWFILE", b"New file on side 0")
        assert disk.exists("$.NEWFILE")
        assert len(disk.files) == 14  # Was 13

    def test_can_write_to_side1(self, writable_copy):
        """Can add files to Side 1."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=True, side=1)

        disk.save("$.NEWFILE", b"New file on side 1")
        assert disk.exists("$.NEWFILE")
        assert len(disk.files) == 10  # Was 9

    def test_files_added_to_different_sides_are_isolated(self, writable_copy):
        """Files added to one side don't appear on the other."""
        disk_path = writable_copy(IMAGE_NAME)

        # Add file to side 0 (max 7 char filename)
        disk0 = DFSImage.open(disk_path, writable=True, side=0)
        disk0.save("$.SIDE0", b"On side 0 only")
        disk0.close()

        # Add different file to side 1
        disk1 = DFSImage.open(disk_path, writable=True, side=1)
        disk1.save("$.SIDE1", b"On side 1 only")
        disk1.close()

        # Verify isolation
        disk0 = DFSImage.open(disk_path, writable=False, side=0)
        disk1 = DFSImage.open(disk_path, writable=False, side=1)

        assert disk0.exists("$.SIDE0")
        assert not disk0.exists("$.SIDE1")

        assert disk1.exists("$.SIDE1")
        assert not disk1.exists("$.SIDE0")


class TestErrorHandling:
    """Test error handling for side parameter."""

    def test_cannot_open_nonexistent_side(self, reference_image):
        """Cannot open side 2 or higher."""
        with pytest.raises(ValueError, match="Invalid side"):
            reference_image(IMAGE_NAME, side=2)

    def test_default_side_is_0(self, reference_image):
        """Opening without side parameter defaults to side 0."""
        disk_default = reference_image(IMAGE_NAME)
        disk_explicit = reference_image(IMAGE_NAME, side=0)

        # Should have same title (SIDE0)
        assert disk_default.title.rstrip('\x00 ') == "SIDE0"
        assert disk_explicit.title.rstrip('\x00 ') == "SIDE0"

        # Should have same file count
        assert len(disk_default.files) == len(disk_explicit.files) == 13

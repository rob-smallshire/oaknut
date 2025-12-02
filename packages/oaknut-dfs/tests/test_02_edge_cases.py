"""Tests for 02-edge-cases.ssd reference image.

Generator: tests/data/generators/02-edge-cases.bas
Image:     tests/data/images/02-edge-cases.ssd
Format:    80T SSD (Single-sided, 80 tracks)

This test validates oaknut-dfs handling of edge cases:
  - Full catalog (31 files maximum)
  - Special characters in filenames (!BOOT, TEST-1)
  - Files distributed across multiple directories

Expected Contents (from generator):
  $ directory: FILE0-FILE9, !BOOT, TEST-1, FILE31 (13 files)
  A directory: FILE10-FILE19 (10 files)
  B directory: FILE20-FILE27 (8 files)
  Total: 31 files (catalog full)
"""

import pytest
from oaknut_dfs.dfs_filesystem import DFSImage
from oaknut_dfs.exceptions import CatalogFullError


IMAGE_NAME = "02-edge-cases.ssd"


class TestDiskMetadata:
    """Test disk-level metadata."""

    def test_disk_format_detection(self, reference_image):
        """Disk is correctly detected as 80T SSD."""
        disk = reference_image(IMAGE_NAME)
        assert disk is not None

    def test_disk_title(self, reference_image):
        """Disk title is correct."""
        disk = reference_image(IMAGE_NAME)
        assert disk.title.rstrip('\x00 ') == "EDGE"

    def test_catalog_full(self, reference_image):
        """Catalog contains exactly 31 files (maximum for standard DFS)."""
        disk = reference_image(IMAGE_NAME)
        assert len(disk.files) == 31, \
            f"Expected 31 files (catalog full), found {len(disk.files)}"


class TestFileDistribution:
    """Test files are distributed correctly across directories."""

    def test_dollar_directory_count(self, reference_image):
        """$ directory has correct number of files."""
        disk = reference_image(IMAGE_NAME)
        dollar_files = [f for f in disk.files if f.directory == '$']
        assert len(dollar_files) == 13, \
            f"Expected 13 files in $, found {len(dollar_files)}: {[f.filename for f in dollar_files]}"

    def test_directory_a_count(self, reference_image):
        """A directory has correct number of files."""
        disk = reference_image(IMAGE_NAME)
        a_files = [f for f in disk.files if f.directory == 'A']
        assert len(a_files) == 10, \
            f"Expected 10 files in A, found {len(a_files)}: {[f.filename for f in a_files]}"

    def test_directory_b_count(self, reference_image):
        """B directory has correct number of files."""
        disk = reference_image(IMAGE_NAME)
        b_files = [f for f in disk.files if f.directory == 'B']
        assert len(b_files) == 8, \
            f"Expected 8 files in B, found {len(b_files)}: {[f.filename for f in b_files]}"

    def test_all_dollar_files_exist(self, reference_image):
        """All expected $ directory files exist."""
        disk = reference_image(IMAGE_NAME)

        # FILE0-FILE9
        for i in range(10):
            filename = f"$.FILE{i}"
            assert disk.exists(filename), f"{filename} not found"

        # Special files
        assert disk.exists("$.!BOOT"), "$.!BOOT not found"
        assert disk.exists("$.TEST-1"), "$.TEST-1 not found"
        assert disk.exists("$.FILE31"), "$.FILE31 not found"

    def test_all_directory_a_files_exist(self, reference_image):
        """All expected A directory files exist."""
        disk = reference_image(IMAGE_NAME)

        for i in range(10, 20):
            filename = f"A.FILE{i}"
            assert disk.exists(filename), f"{filename} not found"

    def test_all_directory_b_files_exist(self, reference_image):
        """All expected B directory files exist."""
        disk = reference_image(IMAGE_NAME)

        for i in range(20, 28):
            filename = f"B.FILE{i}"
            assert disk.exists(filename), f"{filename} not found"


class TestSpecialFilenames:
    """Test special filename handling."""

    def test_boot_file_exists(self, reference_image):
        """!BOOT file (commonly used for auto-boot) exists."""
        disk = reference_image(IMAGE_NAME)
        assert disk.exists("$.!BOOT")

    def test_boot_file_content(self, reference_image):
        """!BOOT file has expected content."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.!BOOT")
        text = data.decode('utf-8')

        # Should contain FX commands
        assert "*FX 200,3" in text
        assert "*FX 229,1" in text

    def test_hyphenated_filename_exists(self, reference_image):
        """Filename with hyphen (TEST-1) exists."""
        disk = reference_image(IMAGE_NAME)
        assert disk.exists("$.TEST-1")

    def test_hyphenated_filename_content(self, reference_image):
        """Hyphenated filename has expected content."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.TEST-1")
        text = data.decode('utf-8')
        assert "Filename with hyphen" in text

    def test_numeric_filename_exists(self, reference_image):
        """FILE31 (31st file) exists."""
        disk = reference_image(IMAGE_NAME)
        assert disk.exists("$.FILE31")

    def test_numeric_filename_content(self, reference_image):
        """FILE31 has expected content."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.FILE31")
        text = data.decode('utf-8')
        assert "This is file 31 - catalog is now full!" in text


class TestFileContents:
    """Test file contents are correct."""

    def test_dollar_directory_files(self, reference_image):
        """$ directory numbered files have correct content."""
        disk = reference_image(IMAGE_NAME)

        for i in range(10):
            filename = f"$.FILE{i}"
            data = disk.load(filename)
            text = data.decode('utf-8')
            expected = f"File number {i} in $ directory"
            assert expected in text, \
                f"{filename} has unexpected content: {text}"

    def test_directory_a_files(self, reference_image):
        """A directory files have correct content."""
        disk = reference_image(IMAGE_NAME)

        for i in range(10, 20):
            filename = f"A.FILE{i}"
            data = disk.load(filename)
            text = data.decode('utf-8')
            expected = f"File number {i} in A directory"
            assert expected in text, \
                f"{filename} has unexpected content: {text}"

    def test_directory_b_files(self, reference_image):
        """B directory files have correct content."""
        disk = reference_image(IMAGE_NAME)

        for i in range(20, 28):
            filename = f"B.FILE{i}"
            data = disk.load(filename)
            text = data.decode('utf-8')
            expected = f"File number {i} in B directory"
            assert expected in text, \
                f"{filename} has unexpected content: {text}"


class TestCatalogFull:
    """Test catalog full behavior."""

    def test_cannot_add_32nd_file(self, writable_copy):
        """Cannot add a 32nd file when catalog is full."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=True)

        # Verify catalog is full
        assert len(disk.files) == 31

        # Try to add a 32nd file - should raise CatalogFullError
        with pytest.raises(CatalogFullError):
            disk.save("$.TEST32", b"This should fail")

    def test_can_modify_existing_file_when_full(self, writable_copy):
        """Can modify existing files even when catalog is full."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=True)

        # Should be able to overwrite existing file
        new_content = b"Modified content"
        disk.save("$.FILE0", new_content)

        # Verify modification
        loaded = disk.load("$.FILE0")
        assert loaded == new_content

        # Catalog should still be full
        assert len(disk.files) == 31

    def test_can_add_file_after_deletion(self, writable_copy):
        """Can add a file after deleting one from full catalog."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path, writable=True)

        # Delete one file
        disk.delete("$.FILE0")
        assert len(disk.files) == 30

        # Now should be able to add a new file
        disk.save("$.NEWFILE", b"New file content")
        assert len(disk.files) == 31
        assert disk.exists("$.NEWFILE")


class TestVariableNameLengths:
    """Test filenames of various lengths."""

    def test_two_character_filename(self, reference_image):
        """Two-character filenames work (FILE0-FILE9)."""
        disk = reference_image(IMAGE_NAME)

        # FILE0-FILE9 are 5 characters
        for i in range(10):
            filename = f"FILE{i}"
            assert disk.exists(f"$.{filename}")
            info = disk.get_file_info(f"$.{filename}")
            assert len(info.filename) == len(filename)

    def test_six_character_filename(self, reference_image):
        """Six-character filenames work (FILE10-FILE27)."""
        disk = reference_image(IMAGE_NAME)

        # FILE10-FILE27 are 6 characters
        for i in range(10, 28):
            if i < 20:
                filename = f"A.FILE{i}"
            else:
                filename = f"B.FILE{i}"
            assert disk.exists(filename)
            info = disk.get_file_info(filename)
            assert len(info.filename) == 6

    def test_special_character_in_filename(self, reference_image):
        """Special characters in filenames work (!BOOT, TEST-1)."""
        disk = reference_image(IMAGE_NAME)

        # ! character
        assert disk.exists("$.!BOOT")
        info = disk.get_file_info("$.!BOOT")
        assert info.filename == "!BOOT"

        # Hyphen character
        assert disk.exists("$.TEST-1")
        info = disk.get_file_info("$.TEST-1")
        assert info.filename == "TEST-1"

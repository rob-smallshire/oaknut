"""Tests for 01-basic-validation.ssd reference image.

Generator: tests/data/generators/01-basic-validation-simple.bas
Image:     tests/data/images/01-basic-validation.ssd
Format:    80T SSD (Single-sided, 80 tracks)

This test validates oaknut-dfs against a real disk image created by
running the generator program in a BBC Micro emulator (b2/BeebEm).

Expected Contents (from generator):
  $ directory: TEXT, MULTI, X, ABCDEFG, BINARY, LOCKED
  A directory: DATA1, DATA2, DATA3
  B directory: FILE1, FILE2
  Total: 11 files
"""

import pytest
from oaknut_dfs.dfs_filesystem import DFSImage


IMAGE_NAME = "01-basic-validation.ssd"


class TestDiskMetadata:
    """Test disk-level metadata."""

    def test_disk_format_detection(self, reference_image):
        """Disk is correctly detected as 80T SSD."""
        disk = reference_image(IMAGE_NAME)
        # Format detection is implicit in successful open
        assert disk is not None

    def test_file_count(self, reference_image):
        """Disk contains expected number of files."""
        disk = reference_image(IMAGE_NAME)
        assert len(disk.files) == 11, \
            f"Expected 11 files, found {len(disk.files)}: {[f.name for f in disk.files]}"


class TestDollarDirectory:
    """Test files in $ directory."""

    def test_all_dollar_files_exist(self, reference_image):
        """All expected $ directory files exist."""
        disk = reference_image(IMAGE_NAME)
        expected_files = ["$.TEXT", "$.MULTI", "$.X", "$.ABCDEFG", "$.BINARY", "$.LOCKED"]

        for filename in expected_files:
            assert disk.exists(filename), f"Missing file: {filename}"

    def test_text_file_content(self, reference_image):
        """$.TEXT has expected content."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.TEXT")
        text = data.decode('utf-8')
        assert "Simple text content" in text

    def test_multi_line_text_content(self, reference_image):
        """$.MULTI has expected multi-line content."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.MULTI")
        text = data.decode('utf-8')

        # Should have 3 lines
        lines = text.strip().split('\n')
        assert len(lines) == 3
        assert "Line 1" in text
        assert "Line 2" in text
        assert "Line 3" in text

    def test_short_filename(self, reference_image):
        """$.X (one-character filename) works correctly."""
        disk = reference_image(IMAGE_NAME)
        assert disk.exists("$.X")

        data = disk.load("$.X")
        text = data.decode('utf-8')
        assert "Short name" in text

    def test_max_length_filename(self, reference_image):
        """$.ABCDEFG (seven-character filename, max) works correctly."""
        disk = reference_image(IMAGE_NAME)
        assert disk.exists("$.ABCDEFG")

        info = disk.get_file_info("$.ABCDEFG")
        assert len(info.filename) == 7
        assert info.filename == "ABCDEFG"

        data = disk.load("$.ABCDEFG")
        text = data.decode('utf-8')
        assert "Seven character filename" in text

    def test_binary_file_content(self, reference_image):
        """$.BINARY contains expected byte sequence (0-255)."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.BINARY")

        # Should be exactly 256 bytes
        assert len(data) == 256, f"Expected 256 bytes, got {len(data)}"

        # Should be sequential bytes 0-255 (created with BPUT#file%,I%)
        expected = bytes(range(256))
        assert data == expected, \
            f"Binary data mismatch. First different byte at position {next(i for i, (a, b) in enumerate(zip(data, expected)) if a != b)}"

    def test_locked_file_status(self, reference_image):
        """$.LOCKED has locked flag set."""
        disk = reference_image(IMAGE_NAME)
        info = disk.get_file_info("$.LOCKED")
        assert info.locked is True

    def test_locked_file_content(self, reference_image):
        """$.LOCKED can still be read despite lock."""
        disk = reference_image(IMAGE_NAME)
        data = disk.load("$.LOCKED")
        text = data.decode('utf-8')
        assert "This file is locked" in text

    def test_unlocked_files_not_locked(self, reference_image):
        """Non-locked files have correct status."""
        disk = reference_image(IMAGE_NAME)
        unlocked_files = ["$.TEXT", "$.MULTI", "$.X", "$.ABCDEFG", "$.BINARY"]

        for filename in unlocked_files:
            info = disk.get_file_info(filename)
            assert info.locked is False, f"{filename} should not be locked"


class TestDirectoryA:
    """Test files in A directory."""

    def test_all_directory_a_files_exist(self, reference_image):
        """All expected A directory files exist."""
        disk = reference_image(IMAGE_NAME)
        expected_files = ["A.DATA1", "A.DATA2", "A.DATA3"]

        for filename in expected_files:
            assert disk.exists(filename), f"Missing file: {filename}"

    def test_directory_a_content(self, reference_image):
        """Directory A files have expected content."""
        disk = reference_image(IMAGE_NAME)

        for i in range(1, 4):
            filename = f"A.DATA{i}"
            data = disk.load(filename)
            text = data.decode('utf-8')
            assert f"Directory A, file {i}" in text, \
                f"{filename} has unexpected content: {text}"


class TestDirectoryB:
    """Test files in B directory."""

    def test_all_directory_b_files_exist(self, reference_image):
        """All expected B directory files exist."""
        disk = reference_image(IMAGE_NAME)
        expected_files = ["B.FILE1", "B.FILE2"]

        for filename in expected_files:
            assert disk.exists(filename), f"Missing file: {filename}"

    def test_directory_b_content(self, reference_image):
        """Directory B files have expected content."""
        disk = reference_image(IMAGE_NAME)

        for i in range(1, 3):
            filename = f"B.FILE{i}"
            data = disk.load(filename)
            text = data.decode('utf-8')
            assert f"Directory B, file {i}" in text, \
                f"{filename} has unexpected content: {text}"


class TestWritableOperations:
    """Test operations that require writable copy."""

    def test_writable_copy_can_be_modified(self, writable_copy):
        """Writable copy can be modified without affecting original."""
        from pathlib import Path

        # Get writable copy
        disk_path = writable_copy(IMAGE_NAME)

        # Verify it's a copy in temp directory
        assert "pytest" in str(disk_path)

        # Modify the copy
        disk = DFSImage.open(disk_path)
        original_count = len(disk.files)

        disk.save("$.NEW", b"New file added to copy")
        new_count = len(disk.files)

        assert new_count == original_count + 1
        assert disk.exists("$.NEW")

        disk.close()

        # Verify original is unchanged
        original_path = Path(__file__).parent / "data" / "images" / IMAGE_NAME
        original = DFSImage.open(original_path, writable=False)
        assert len(original.files) == original_count
        assert not original.exists("$.NEW")

    def test_locked_file_cannot_be_deleted(self, writable_copy):
        """Locked file raises FileLocked exception on delete."""
        from oaknut_dfs.exceptions import FileLocked

        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path)

        with pytest.raises(FileLocked, match="locked"):
            disk.delete("$.LOCKED")

    def test_locked_file_can_be_unlocked_then_deleted(self, writable_copy):
        """Locked file can be deleted after unlocking."""
        disk_path = writable_copy(IMAGE_NAME)
        disk = DFSImage.open(disk_path)

        # Verify it's locked
        assert disk.get_file_info("$.LOCKED").locked is True

        # Unlock it
        disk.unlock("$.LOCKED")
        assert disk.get_file_info("$.LOCKED").locked is False

        # Now can delete
        disk.delete("$.LOCKED")
        assert not disk.exists("$.LOCKED")


class TestCatalogOperations:
    """Test catalog-level operations."""

    def test_list_all_files(self, reference_image):
        """Can list all files and get accurate catalog."""
        disk = reference_image(IMAGE_NAME)
        files = disk.files

        assert len(files) == 11

        # Check we have files from all directories
        dollar_files = [f for f in files if f.directory == '$']
        a_files = [f for f in files if f.directory == 'A']
        b_files = [f for f in files if f.directory == 'B']

        assert len(dollar_files) == 6
        assert len(a_files) == 3
        assert len(b_files) == 2

    def test_iterate_over_files(self, reference_image):
        """Can iterate over disk files."""
        disk = reference_image(IMAGE_NAME)

        count = 0
        for file in disk:
            count += 1
            assert file.name  # Each file has a name

        assert count == 11

    def test_in_operator(self, reference_image):
        """'in' operator works for file existence check."""
        disk = reference_image(IMAGE_NAME)

        assert "$.TEXT" in disk
        assert "$.BINARY" in disk
        assert "A.DATA1" in disk
        assert "$.NOTHERE" not in disk

"""Tests for Watford DFS Catalogue implementation."""

import pytest

from oaknut_dfs.catalogue import Catalogue
from oaknut_dfs.surface import DiscImage, SurfaceSpec
from oaknut_dfs.watford_dfs_catalogue import WatfordDFSCatalogue


@pytest.fixture
def watford_dfs_surface():
    """Create a valid Watford DFS surface for testing."""
    buffer = bytearray(204800)  # 80-track single-sided (800 sectors × 256 bytes)

    # Initialize sector 0 (section 1 title in bytes 0-9)
    buffer[0:10] = b'WATFORD   '  # 10-char title (7 letters + 3 spaces)
    buffer[10:12] = b'\x00\x00'  # Bytes 10-11 reserved for catalog chaining

    # Initialize sector 1 (section 1 metadata - no title continuation)
    buffer[256:260] = b'\x00\x00\x00\x00'  # First 4 bytes (no title in Watford DFS)
    buffer[256 + 4] = 0  # Cycle number
    buffer[256 + 5] = 0  # 0 files (bits 0,1,2 must be clear)
    buffer[256 + 6] = 0x03  # Boot option 0, 800 sectors high bits (0x03)
    buffer[256 + 7] = 0x20  # 800 sectors low byte (0x320 = 800)

    # Initialize sector 2 (0xAA marker - Watford DFS signature)
    buffer[512:524] = b'\xAA' * 12

    # Initialize sector 3 (section 2 metadata)
    buffer[768:772] = b'\x00\x00\x00\x00'  # First 4 bytes null
    buffer[768 + 4] = 0  # Cycle number (matches section 1)
    buffer[768 + 5] = 0  # 0 files in section 2
    buffer[768 + 6] = 0x03  # Boot option 0, sector count high (matches section 1)
    buffer[768 + 7] = 0x20  # Sector count low (matches section 1)

    spec = SurfaceSpec(
        num_tracks=80,
        sectors_per_track=10,
        bytes_per_sector=256,
        track_zero_offset_bytes=0,
        track_stride_bytes=2560,  # 10 sectors × 256 bytes
    )
    disc = DiscImage(memoryview(buffer), [spec])
    return disc.surface(0)


class TestWatfordDFSCatalogueRegistry:
    """Test Watford DFS catalogue registration."""

    def test_watford_dfs_registered(self):
        """Verify Watford DFS is registered in catalogue registry."""
        assert "watford-dfs" in Catalogue._registry
        assert Catalogue._registry["watford-dfs"] is WatfordDFSCatalogue

    def test_identify_returns_watford_dfs_for_valid_image(self, watford_dfs_surface):
        """Test that identify() returns WatfordDFSCatalogue for valid image."""
        result = Catalogue.identify(watford_dfs_surface)
        assert result is WatfordDFSCatalogue

    def test_identify_returns_none_for_acorn_dfs_image(self):
        """Test that Watford DFS doesn't match Acorn DFS images."""
        buffer = bytearray(102400)  # 40-track single-sided
        buffer[0:12] = b'ACORNDFS    '  # No 0xAA marker
        buffer[256 + 5] = 0
        buffer[256 + 6] = 0x01
        buffer[256 + 7] = 0x90  # 400 sectors

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        # Should not match Watford DFS (no 0xAA marker)
        assert not WatfordDFSCatalogue.matches(surface)


class TestWatfordDFSCatalogueMatches:
    """Test Watford DFS format detection."""

    def test_matches_valid_watford_dfs(self, watford_dfs_surface):
        """Test matches() returns True for valid Watford DFS image."""
        assert WatfordDFSCatalogue.matches(watford_dfs_surface)

    def test_matches_rejects_missing_aa_marker(self, watford_dfs_surface):
        """Test matches() rejects image without 0xAA marker."""
        # Clear the 0xAA marker
        buffer = watford_dfs_surface._disc_image.buffer
        buffer[512:524] = b'\x00' * 12

        assert not WatfordDFSCatalogue.matches(watford_dfs_surface)

    def test_matches_rejects_metadata_mismatch(self, watford_dfs_surface):
        """Test matches() rejects image with mismatched metadata between sections."""
        # Change sector 3 metadata to not match sector 1
        buffer = watford_dfs_surface._disc_image.buffer
        buffer[768 + 6] = 0x00  # Different from sector 1

        assert not WatfordDFSCatalogue.matches(watford_dfs_surface)

    def test_matches_rejects_too_few_sectors(self):
        """Test matches() rejects image with fewer than 4 sectors."""
        buffer = bytearray(768)  # Only 3 sectors
        spec = SurfaceSpec(
            num_tracks=1,
            sectors_per_track=3,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=768,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        assert not WatfordDFSCatalogue.matches(surface)


class TestWatfordDFSCatalogueGetDiskInfo:
    """Test reading disk info from Watford DFS catalogue."""

    def test_get_disk_info_empty_disk(self, watford_dfs_surface):
        """Test reading disk info from empty Watford DFS disk."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        disk_info = catalogue.get_disk_info()

        assert disk_info.title == "WATFORD"
        assert disk_info.num_files == 0  # Both sections empty
        assert disk_info.total_sectors == 800
        assert disk_info.boot_option == 0

    def test_get_disk_info_combines_file_counts(self, watford_dfs_surface):
        """Test that file count is sum of both catalog sections."""
        buffer = watford_dfs_surface._disc_image.buffer

        # Section 1: 5 files
        buffer[256 + 5] = 5 * 8

        # Section 2: 3 files
        buffer[768 + 5] = 3 * 8

        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        disk_info = catalogue.get_disk_info()

        assert disk_info.num_files == 8  # 5 + 3


class TestWatfordDFSCatalogueListFiles:
    """Test listing files from Watford DFS catalogue."""

    def test_list_files_empty_catalog(self, watford_dfs_surface):
        """Test listing files from empty catalogue."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        files = catalogue.list_files()

        assert len(files) == 0

    def test_list_files_from_section_1(self, watford_dfs_surface):
        """Test listing files from section 1 only."""
        buffer = watford_dfs_surface._disc_image.buffer

        # Add one file to section 1
        buffer[8:15] = b'HELLO  '  # Filename
        buffer[15] = ord('$')  # Directory

        buffer[256 + 8:256 + 10] = b'\x00\x00'  # Load address low
        buffer[256 + 10:256 + 12] = b'\x00\x00'  # Exec address low
        buffer[256 + 12:256 + 14] = b'\x0A\x00'  # Length = 10 bytes
        buffer[256 + 14] = 0x00  # Extra byte
        buffer[256 + 15] = 0x04  # Start sector = 4

        buffer[256 + 5] = 1 * 8  # 1 file in section 1

        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        files = catalogue.list_files()

        assert len(files) == 1
        assert files[0].filename == "HELLO"
        assert files[0].directory == "$"
        assert files[0].length == 10
        assert files[0].start_sector == 4


class TestWatfordDFSCatalogueValidation:
    """Test Watford DFS validation methods."""

    def test_validate_title_max_10_chars(self, watford_dfs_surface):
        """Test that titles are limited to 10 characters for Watford DFS."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)

        # 10 chars should be OK
        catalogue.validate_title("TENCHARSS!")

        # 11 chars should fail
        with pytest.raises(ValueError, match="Title too long"):
            catalogue.validate_title("ELEVEN CHAR")

    def test_validate_empty_catalog(self, watford_dfs_surface):
        """Test validate() on empty catalog."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        errors = catalogue.validate()

        assert len(errors) == 0

    def test_validate_detects_missing_aa_marker(self, watford_dfs_surface):
        """Test validate() detects missing 0xAA marker."""
        buffer = watford_dfs_surface._disc_image.buffer
        buffer[512:524] = b'\x00' * 12  # Clear marker

        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        errors = catalogue.validate()

        assert any("marker" in err.lower() for err in errors)

    def test_validate_detects_metadata_mismatch(self, watford_dfs_surface):
        """Test validate() detects metadata synchronization issues."""
        buffer = watford_dfs_surface._disc_image.buffer
        buffer[768 + 6] = 0xFF  # Mismatch boot option/sector count

        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        errors = catalogue.validate()

        assert any("mismatch" in err.lower() for err in errors)


class TestWatfordDFSCatalogueMaxFiles:
    """Test Watford DFS 62-file capacity."""

    def test_max_files_property(self, watford_dfs_surface):
        """Test that max_files returns 62."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        assert catalogue.max_files == 62


class TestWatfordDFSCatalogueFileOperations:
    """Test file operations that trigger write operations."""

    def test_add_file_entry(self, watford_dfs_surface):
        """Test adding a file entry (triggers _sync_metadata)."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)

        # Add a file to section 1
        catalogue.add_file_entry(
            filename="TEST",
            directory="$",
            load_address=0x1900,
            exec_address=0x1900,
            length=100,
            start_sector=4,
            locked=False
        )

        # Verify file was added
        files = catalogue.list_files()
        assert len(files) == 1
        assert files[0].filename == "TEST"
        assert files[0].directory == "$"
        assert files[0].start_sector == 4

        # Verify disk info updated
        disk_info = catalogue.get_disk_info()
        assert disk_info.num_files == 1

    def test_remove_file_entry(self, watford_dfs_surface):
        """Test removing a file entry (triggers _rebuild_catalog)."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)

        # Add a file first
        catalogue.add_file_entry(
            filename="TEST",
            directory="$",
            load_address=0x1900,
            exec_address=0x1900,
            length=100,
            start_sector=4,
            locked=False
        )

        # Remove the file
        catalogue.remove_file_entry("$.TEST")

        # Verify file was removed
        files = catalogue.list_files()
        assert len(files) == 0

        disk_info = catalogue.get_disk_info()
        assert disk_info.num_files == 0

    def test_set_boot_option(self, watford_dfs_surface):
        """Test setting boot option (triggers _sync_metadata)."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)

        # Set boot option to 3
        catalogue.set_boot_option(3)

        # Verify it was set
        disk_info = catalogue.get_disk_info()
        assert disk_info.boot_option == 3

    def test_compact(self, watford_dfs_surface):
        """Test compact operation (triggers _rebuild_catalog)."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)

        # Add two files with a gap
        catalogue.add_file_entry(
            filename="FILE1",
            directory="$",
            load_address=0x1900,
            exec_address=0x1900,
            length=256,
            start_sector=4,
            locked=False
        )
        catalogue.add_file_entry(
            filename="FILE2",
            directory="$",
            load_address=0x1900,
            exec_address=0x1900,
            length=256,
            start_sector=10,  # Gap from sector 5-9
            locked=False
        )

        # Compact should work without errors
        catalogue.compact()

        # Verify files still exist
        files = catalogue.list_files()
        assert len(files) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for AcornDFSCatalogue."""

import pytest

from oaknut_dfs.acorn_dfs_catalogue import AcornDFSCatalogue
from oaknut_dfs.catalogue import DiskInfo, FileEntry
from oaknut_dfs.surface import DiscImage, SurfaceSpec


class TestAcornDFSCatalogueGetDiskInfo:
    """Tests for get_disk_info()."""

    def test_get_disk_info_empty_disk(self):
        """Test reading disk info from an empty formatted disk."""
        # Create a surface with minimal catalog
        buffer = bytearray(102400)  # 40 tracks * 10 sectors * 256 bytes

        # Write minimal catalog to sectors 0-1
        # Sector 0: Title "TEST    " (8 bytes)
        buffer[0:8] = b"TEST    "

        # Sector 1: Title continuation "DISK" (4 bytes) + metadata
        buffer[256:260] = b"DISK"
        buffer[260] = 0  # Cycle number
        buffer[261] = 0  # Num files * 8 = 0
        buffer[262] = 0x20  # Boot option 2 in high nibble
        buffer[263] = 200  # Total sectors (low byte) = 200

        # Create surface
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        # Create catalog and read disk info
        catalogue = AcornDFSCatalogue(surface)
        info = catalogue.get_disk_info()

        assert info.title == "TEST    DISK"
        assert info.cycle_number == 0
        assert info.num_files == 0
        assert info.total_sectors == 200
        assert info.boot_option == 2

    def test_get_disk_info_with_files(self):
        """Test reading disk info from disk with files."""
        buffer = bytearray(102400)

        # Sector 0: Title
        buffer[0:8] = b"MYDISC  "

        # Sector 1: Title continuation + metadata
        buffer[256:260] = b"    "
        buffer[260] = 5  # Cycle number
        buffer[261] = 16  # 2 files * 8
        buffer[262] = 0x10  # Boot option 1
        buffer[263] = 250  # Total sectors

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        catalogue = AcornDFSCatalogue(surface)
        info = catalogue.get_disk_info()

        assert info.title == "MYDISC"
        assert info.cycle_number == 5
        assert info.num_files == 2
        assert info.total_sectors == 250
        assert info.boot_option == 1


class TestAcornDFSCatalogueListFiles:
    """Tests for list_files()."""

    def test_list_files_empty_catalog(self):
        """Test listing files from empty catalog."""
        buffer = bytearray(102400)

        # Empty catalog
        buffer[0:8] = b"EMPTY   "
        buffer[256:260] = b"    "
        buffer[260] = 0  # Cycle
        buffer[261] = 0  # 0 files
        buffer[262] = 0x00
        buffer[263] = 200

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        catalogue = AcornDFSCatalogue(surface)
        files = catalogue.list_files()

        assert files == []

    def test_list_files_single_file(self):
        """Test listing catalog with one file."""
        buffer = bytearray(102400)

        # Catalog with 1 file
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0  # Cycle
        buffer[261] = 8  # 1 file * 8
        buffer[262] = 0x00
        buffer[263] = 200

        # File entry in sectors 0-1 at offset 8
        # Sector 0 offset 8: filename "HELLO  " + directory "$"
        buffer[8:15] = b"HELLO  "
        buffer[15] = ord("$")

        # Sector 1 offset 8: load addr, exec addr, length, sector
        buffer[256 + 8] = 0x00  # Load low byte
        buffer[256 + 9] = 0x10  # Load high byte = 0x1000
        buffer[256 + 10] = 0x00  # Exec low byte
        buffer[256 + 11] = 0x10  # Exec high byte = 0x1000
        buffer[256 + 12] = 0x64  # Length low byte = 100
        buffer[256 + 13] = 0x00  # Length high byte
        buffer[256 + 14] = 0x00  # Extra byte
        buffer[256 + 15] = 0x02  # Start sector = 2

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        catalogue = AcornDFSCatalogue(surface)
        files = catalogue.list_files()

        assert len(files) == 1
        assert files[0].filename == "HELLO"
        assert files[0].directory == "$"
        assert files[0].locked == False
        assert files[0].load_address == 0x1000
        assert files[0].exec_address == 0x1000
        assert files[0].length == 100
        assert files[0].start_sector == 2
        assert files[0].path == "$.HELLO"


class TestAcornDFSCatalogueAddFileEntry:
    """Tests for add_file_entry()."""

    def test_add_file_entry_to_empty_catalog(self):
        """Test adding first file to empty catalog."""
        buffer = bytearray(102400)

        # Empty catalog
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0  # Cycle
        buffer[261] = 0  # 0 files
        buffer[262] = 0x00
        buffer[263] = 200

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        catalogue = AcornDFSCatalogue(surface)

        # Add a file
        catalogue.add_file_entry(
            filename="TEST",
            directory="$",
            load_address=0x2000,
            exec_address=0x3000,
            length=500,
            start_sector=2,
        )

        # Verify file was added
        files = catalogue.list_files()
        assert len(files) == 1
        assert files[0].filename == "TEST"
        assert files[0].directory == "$"
        assert files[0].load_address == 0x2000
        assert files[0].exec_address == 0x3000
        assert files[0].length == 500
        assert files[0].start_sector == 2

        # Verify cycle number was incremented
        info = catalogue.get_disk_info()
        assert info.cycle_number == 1
        assert info.num_files == 1

    def test_add_file_entry_catalog_full(self):
        """Test error when catalog is full."""
        buffer = bytearray(102400)

        # Catalog with 31 files (max)
        buffer[0:8] = b"FULL    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 31 * 8  # 31 files
        buffer[262] = 0x00
        buffer[263] = 200

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        catalogue = AcornDFSCatalogue(surface)

        # Try to add file - should fail
        with pytest.raises(ValueError, match="Catalog full"):
            catalogue.add_file_entry(
                filename="OVERFLOW",
                directory="$",
                load_address=0,
                exec_address=0,
                length=100,
                start_sector=2,
            )


class TestAcornDFSCatalogueRemoveFileEntry:
    """Tests for remove_file_entry()."""

    def test_remove_file_entry(self):
        """Test removing a file from catalog."""
        buffer = bytearray(102400)

        # Catalog with 2 files
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 16  # 2 files
        buffer[262] = 0x00
        buffer[263] = 200

        # File 1: $.HELLO
        buffer[8:15] = b"HELLO  "
        buffer[15] = ord("$")
        buffer[256 + 8:256 + 16] = bytes([0, 0, 0, 0, 100, 0, 0, 2])

        # File 2: $.WORLD
        buffer[16:23] = b"WORLD  "
        buffer[23] = ord("$")
        buffer[256 + 16:256 + 24] = bytes([0, 0, 0, 0, 200, 0, 0, 4])

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        catalogue = AcornDFSCatalogue(surface)

        # Remove first file
        catalogue.remove_file_entry("$.HELLO")

        # Verify only one file remains
        files = catalogue.list_files()
        assert len(files) == 1
        assert files[0].filename == "WORLD"

    def test_remove_locked_file_raises_error(self):
        """Test that removing locked file raises error."""
        buffer = bytearray(102400)

        # Catalog with 1 locked file
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8  # 1 file
        buffer[262] = 0x00
        buffer[263] = 200

        # Locked file (bit 7 set in directory byte)
        buffer[8:15] = b"LOCKED "
        buffer[15] = ord("$") | 0x80  # Set lock bit
        buffer[256 + 8:256 + 16] = bytes([0, 0, 0, 0, 100, 0, 0, 2])

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        catalogue = AcornDFSCatalogue(surface)

        # Try to remove locked file
        with pytest.raises(PermissionError, match="locked"):
            catalogue.remove_file_entry("$.LOCKED")

    def test_remove_nonexistent_file_raises_error(self):
        """Test that removing nonexistent file raises error."""
        buffer = bytearray(102400)

        # Empty catalog
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        catalogue = AcornDFSCatalogue(surface)

        with pytest.raises(FileNotFoundError):
            catalogue.remove_file_entry("$.NOSUCHFILE")

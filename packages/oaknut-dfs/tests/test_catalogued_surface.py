"""Tests for CataloguedSurface."""

import pytest

from oaknut_dfs.acorn_dfs_catalogue import AcornDFSCatalogue
from oaknut_dfs.catalogued_surface import CataloguedSurface
from oaknut_dfs.surface import DiscImage, SurfaceSpec


class TestCataloguedSurfaceReadFile:
    """Tests for read_file()."""

    def test_read_file_simple(self):
        """Test reading a file from catalogued surface."""
        buffer = bytearray(102400)

        # Create catalog with 1 file
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8  # 1 file
        buffer[262] = 0x00
        buffer[263] = 200

        # File entry: $.TEST at sector 2, length 100
        buffer[8:15] = b"TEST   "
        buffer[15] = ord("$")
        buffer[256 + 8] = 0x00  # Load addr low
        buffer[256 + 9] = 0x10  # Load addr high
        buffer[256 + 10] = 0x00  # Exec addr low
        buffer[256 + 11] = 0x10  # Exec addr high
        buffer[256 + 12] = 100  # Length low byte = 100
        buffer[256 + 13] = 0  # Length high byte
        buffer[256 + 14] = 0x00  # Extra byte
        buffer[256 + 15] = 2  # Start sector = 2

        # Write file data to sector 2
        file_data = b"Hello, World!" * 7 + b"X"  # 92 bytes
        buffer[2 * 256 : 2 * 256 + 100] = file_data.ljust(100)

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)
        data = catalogued.read_file("$.TEST")

        assert len(data) == 100
        assert data[:13] == b"Hello, World!"

    def test_read_file_not_found(self):
        """Test reading nonexistent file raises error."""
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

        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)

        with pytest.raises(FileNotFoundError):
            catalogued.read_file("$.NOSUCHFILE")


class TestCataloguedSurfaceWriteFile:
    """Tests for write_file()."""

    def test_write_file_to_empty_disk(self):
        """Test writing first file to empty disk."""
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

        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)

        # Write a file
        file_data = b"Test file content"
        catalogued.write_file(
            filename="HELLO",
            directory="$",
            data=file_data,
            load_address=0x2000,
            exec_address=0x3000,
        )

        # Verify file was written
        files = catalogued.list_files()
        assert len(files) == 1
        assert files[0].filename == "HELLO"
        assert files[0].directory == "$"
        assert files[0].load_address == 0x2000
        assert files[0].exec_address == 0x3000
        assert files[0].length == len(file_data)
        assert files[0].start_sector == 2  # First free sector after catalog

        # Verify file data
        read_data = catalogued.read_file("$.HELLO")
        assert read_data == file_data

    def test_write_multiple_files(self):
        """Test writing multiple files."""
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

        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)

        # Write first file (1 sector = 256 bytes)
        catalogued.write_file(
            filename="FILE1",
            directory="$",
            data=b"A" * 200,
            load_address=0,
            exec_address=0,
        )

        # Write second file (2 sectors = 512 bytes)
        catalogued.write_file(
            filename="FILE2",
            directory="$",
            data=b"B" * 300,
            load_address=0,
            exec_address=0,
        )

        # Verify both files exist
        files = catalogued.list_files()
        assert len(files) == 2
        assert files[0].filename == "FILE1"
        assert files[0].start_sector == 2
        assert files[0].sectors_required == 1
        assert files[1].filename == "FILE2"
        assert files[1].start_sector == 3  # After FILE1
        assert files[1].sectors_required == 2


class TestCataloguedSurfaceDeleteFile:
    """Tests for delete_file()."""

    def test_delete_file(self):
        """Test deleting a file."""
        buffer = bytearray(102400)

        # Catalog with 2 files
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 16  # 2 files
        buffer[262] = 0x00
        buffer[263] = 200

        # File 1: $.FIRST
        buffer[8:15] = b"FIRST  "
        buffer[15] = ord("$")
        buffer[256 + 8:256 + 16] = bytes([0, 0, 0, 0, 100, 0, 0, 2])

        # File 2: $.SECOND
        buffer[16:23] = b"SECOND "
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

        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)

        # Delete first file
        catalogued.delete_file("$.FIRST")

        # Verify only one file remains
        files = catalogued.list_files()
        assert len(files) == 1
        assert files[0].filename == "SECOND"


class TestCataloguedSurfaceFirstFit:
    """Tests for First Fit allocation algorithm."""

    def test_first_fit_after_catalog(self):
        """Test First Fit finds first free space after catalog."""
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

        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)

        # First free sector should be 2 (after catalog sectors 0-1)
        start = catalogued._first_fit(100)
        assert start == 2

    def test_first_fit_insufficient(self):
        """Test error when not enough free space."""
        buffer = bytearray(2560)  # Only 10 sectors total

        # Empty catalog
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 10

        spec = SurfaceSpec(
            num_tracks=1,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)

        # Try to allocate more than available (8 free sectors after catalog)
        with pytest.raises(IOError, match="Not enough contiguous free space"):
            catalogued._first_fit(10 * 256)  # Need 10 sectors but only 8 free


class TestCataloguedSurfaceIntegration:
    """Integration tests."""

    def test_list_files_delegation(self):
        """Test that list_files delegates to catalog."""
        buffer = bytearray(102400)

        # Catalog with 1 file
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8
        buffer[262] = 0x00
        buffer[263] = 200

        buffer[8:15] = b"TEST   "
        buffer[15] = ord("$")
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

        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)
        files = catalogued.list_files()

        assert len(files) == 1
        assert files[0].filename == "TEST"

    def test_disk_info_delegation(self):
        """Test that disk_info delegates to catalog."""
        buffer = bytearray(102400)

        buffer[0:8] = b"MYDISC  "
        buffer[256:260] = b"    "
        buffer[260] = 5
        buffer[261] = 0
        buffer[262] = 0x10
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

        catalogued = CataloguedSurface(surface, AcornDFSCatalogue)
        info = catalogued.disk_info

        assert info.title == "MYDISC"
        assert info.cycle_number == 5
        assert info.boot_option == 1

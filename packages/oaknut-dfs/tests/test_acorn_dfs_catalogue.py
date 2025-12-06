"""Tests for AcornDFSCatalogue."""

import pytest

import oaknut_dfs.acorn_encoding  # Register codec
from oaknut_dfs.acorn_dfs_catalogue import AcornDFSCatalogue
from oaknut_dfs.catalogue import Catalogue, DiskInfo, FileEntry
from oaknut_dfs.surface import DiscImage, SurfaceSpec


class TestCatalogueRegistry:
    """Tests for Catalogue registry system."""

    def test_acorn_dfs_registered_with_nice_name(self):
        """Test that AcornDFSCatalogue is registered as 'acorn-dfs'."""
        assert "acorn-dfs" in Catalogue._registry
        assert Catalogue._registry["acorn-dfs"] is AcornDFSCatalogue

    def test_identify_returns_acorn_dfs_for_valid_image(self):
        """Test that identify() returns AcornDFSCatalogue for valid image."""
        # Create valid Acorn DFS buffer
        buffer = bytearray(102400)
        buffer[0:8] = b"TESTDISC"
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

        # Identify should return AcornDFSCatalogue
        identified = Catalogue.identify(surface)
        assert identified is AcornDFSCatalogue

    def test_identify_returns_none_for_invalid_image(self):
        """Test that identify() returns None for invalid image."""
        # Create invalid buffer (too small)
        buffer = bytearray(1024)

        spec = SurfaceSpec(
            num_tracks=1,
            sectors_per_track=4,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=1024,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        # Identify should return None
        identified = Catalogue.identify(surface)
        assert identified is None

    def test_missing_catalogue_name_raises_assertion(self):
        """Test that subclass without CATALOGUE_NAME raises AssertionError."""
        with pytest.raises(AssertionError, match="must define CATALOGUE_NAME"):
            # Attempt to create a subclass without CATALOGUE_NAME
            class BadCatalogue(Catalogue):
                CATALOG_START_SECTOR = 0
                CATALOG_NUM_SECTORS = 2

                @classmethod
                def matches(cls, surface):
                    return False

                def get_disk_info(self):
                    pass

                def list_files(self):
                    pass

                def add_file_entry(self, *args, **kwargs):
                    pass

                def remove_file_entry(self, filename):
                    pass

                def set_title(self, title):
                    pass

                def set_boot_option(self, option):
                    pass

                def lock_file(self, filename):
                    pass

                def unlock_file(self, filename):
                    pass

                def rename_file(self, old_name, new_name):
                    pass

                def parse_filename(self, path):
                    pass

                def validate_filename(self, filename):
                    pass

                def validate_directory(self, directory):
                    pass

                def validate_title(self, title):
                    pass

                @property
                def max_files(self):
                    return 0

                def validate(self):
                    return []

                def compact(self):
                    return 0


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

        # Try to add file - should fail (use valid 7-char filename)
        with pytest.raises(ValueError, match="Catalog full"):
            catalogue.add_file_entry(
                filename="FILE32",
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


class TestAcornDFSCatalogueParseFilename:
    """Tests for parse_filename()."""

    def test_parse_filename_with_directory(self):
        """Test parsing filename with directory prefix."""
        buffer = bytearray(102400)
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

        parsed = catalogue.parse_filename("$.HELLO")
        assert parsed.directory == "$"
        assert parsed.filename == "HELLO"
        assert parsed.path == "$.HELLO"

    def test_parse_filename_without_directory_defaults_to_dollar(self):
        """Test parsing bare filename defaults to $ directory."""
        buffer = bytearray(102400)
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

        parsed = catalogue.parse_filename("TEST")
        assert parsed.directory == "$"
        assert parsed.filename == "TEST"
        assert parsed.path == "$.TEST"

    def test_parse_filename_normalizes_to_uppercase(self):
        """Test parse_filename normalizes to uppercase."""
        buffer = bytearray(102400)
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

        parsed = catalogue.parse_filename("a.hello")
        assert parsed.directory == "A"
        assert parsed.filename == "HELLO"

    def test_parse_filename_too_long_raises(self):
        """Test parse_filename raises for filename > 7 chars."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Filename too long"):
            catalogue.parse_filename("$.TOOLONG12")


class TestAcornDFSCatalogueValidateFilename:
    """Tests for validate_filename()."""

    def test_validate_filename_valid(self):
        """Test validate_filename accepts valid filenames."""
        buffer = bytearray(102400)
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

        # Should not raise
        catalogue.validate_filename("HELLO")
        catalogue.validate_filename("TEST123")
        catalogue.validate_filename("A")

    def test_validate_filename_empty_raises(self):
        """Test validate_filename raises for empty filename."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Filename cannot be empty"):
            catalogue.validate_filename("")

    def test_validate_filename_too_long_raises(self):
        """Test validate_filename raises for filename > 7 chars."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Filename too long.*max 7 chars"):
            catalogue.validate_filename("TOOLONGNAME")

    def test_validate_filename_forbids_hash(self):
        """Test validate_filename rejects '#' character."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Forbidden character '#'"):
            catalogue.validate_filename("TEST#1")

    def test_validate_filename_forbids_asterisk(self):
        """Test validate_filename rejects '*' character."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Forbidden character '\\*'"):
            catalogue.validate_filename("TEST*1")

    def test_validate_filename_forbids_colon(self):
        """Test validate_filename rejects ':' character."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Forbidden character ':'"):
            catalogue.validate_filename("TEST:1")

    def test_validate_filename_forbids_dot(self):
        """Test validate_filename rejects '.' character."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Forbidden character '\\.'"):
            catalogue.validate_filename("TEST.1")

    def test_validate_filename_allows_bang_at_start(self):
        """Test validate_filename allows '!' as first character."""
        buffer = bytearray(102400)
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

        # Should not raise
        catalogue.validate_filename("!BOOT")

    def test_validate_filename_forbids_bang_not_at_start(self):
        """Test validate_filename rejects '!' not at first position."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="'!' is only allowed as the first character"):
            catalogue.validate_filename("TEST!")

    def test_validate_filename_forbids_top_bit_set(self):
        """Test validate_filename rejects characters with top bit set."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="has top bit set"):
            catalogue.validate_filename("TEST\x80")

    def test_validate_filename_forbids_control_chars(self):
        """Test validate_filename rejects control characters."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Control character"):
            catalogue.validate_filename("TEST\x01")


class TestAcornDFSCatalogueValidateDirectory:
    """Tests for validate_directory()."""

    def test_validate_directory_valid(self):
        """Test validate_directory accepts valid directories."""
        buffer = bytearray(102400)
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

        # Should not raise
        catalogue.validate_directory("$")
        catalogue.validate_directory("A")
        catalogue.validate_directory("Z")
        catalogue.validate_directory("a")  # Will be normalized to uppercase

    def test_validate_directory_invalid_char_raises(self):
        """Test validate_directory raises for invalid characters."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Invalid directory.*Must be"):
            catalogue.validate_directory("1")

        with pytest.raises(ValueError, match="Invalid directory.*Must be"):
            catalogue.validate_directory("#")

    def test_validate_directory_multi_char_raises(self):
        """Test validate_directory raises for multi-character directory."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Directory must be single character"):
            catalogue.validate_directory("AB")


class TestAcornDFSCatalogueValidateTitle:
    """Tests for validate_title()."""

    def test_validate_title_valid(self):
        """Test validate_title accepts valid titles."""
        buffer = bytearray(102400)
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

        # Should not raise
        catalogue.validate_title("DISK")
        catalogue.validate_title("TEST DISK 12")  # Exactly 12 chars
        catalogue.validate_title("A")

    def test_validate_title_too_long_raises(self):
        """Test validate_title raises for title > 12 chars."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="Title too long.*max 12 chars"):
            catalogue.validate_title("THIS IS TOO LONG")

    def test_validate_title_forbids_top_bit_set(self):
        """Test validate_title rejects characters with top bit set."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="has top bit set"):
            catalogue.validate_title("DISK\x80")

    def test_validate_title_forbids_control_chars(self):
        """Test validate_title rejects control characters."""
        buffer = bytearray(102400)
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

        with pytest.raises(ValueError, match="control character"):
            catalogue.validate_title("DISK\x01")

    def test_validate_title_allows_null_padding(self):
        """Test validate_title allows null character for padding."""
        buffer = bytearray(102400)
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

        # Should not raise - null is allowed for padding
        catalogue.validate_title("DISK\x00\x00\x00")


class TestAcornDFSCatalogueMatches:
    """Tests for matches() classmethod."""

    def test_matches_valid_acorn_dfs(self):
        """Test that valid Acorn DFS is recognized."""
        # Create valid Acorn DFS buffer
        buffer = bytearray(102400)
        buffer[0:8] = b"TESTDISC"
        buffer[256:260] = b"    "
        buffer[260] = 0  # Cycle
        buffer[261] = 0  # 0 files (0 * 8)
        buffer[262] = 0x00  # Boot option 0, bits 2,3,6,7 clear
        buffer[263] = 200  # 200 sectors (40 tracks)

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        assert AcornDFSCatalogue.matches(surface) == True

    def test_matches_valid_acorn_dfs_with_files(self):
        """Test that valid Acorn DFS with files is recognized."""
        buffer = bytearray(102400)
        buffer[0:8] = b"MYDISK  "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8  # 1 file
        buffer[262] = 0x10  # Boot option 1
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

        assert AcornDFSCatalogue.matches(surface) == True

    def test_matches_rejects_watford_dfs_aa_marker(self):
        """Test that Watford DFS with 0xAA marker is rejected."""
        buffer = bytearray(102400)
        # Set up sectors 0-1 like Acorn DFS
        buffer[0:8] = b"TESTDISC"
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        # Add Watford marker to sector 2
        buffer[512:520] = b"\xAA" * 8  # 8 bytes of 0xAA

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        assert AcornDFSCatalogue.matches(surface) == False

    def test_matches_rejects_watford_dfs_full_markers(self):
        """Test that Watford DFS with full markers is rejected."""
        buffer = bytearray(102400)
        # Set up sectors 0-1 like Acorn DFS
        buffer[0:8] = b"TESTDISC"
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        # Add full Watford markers
        buffer[512:520] = b"\xAA" * 8  # Sector 2: 8 bytes of 0xAA
        buffer[768:772] = b"\x00" * 4  # Sector 3: 4 bytes of 0x00
        buffer[773] = 0  # bits 0,1,2 clear
        buffer[774] = 0x00  # Match sector1[6]
        buffer[775] = 200  # Match sector1[7]

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        assert AcornDFSCatalogue.matches(surface) == False

    def test_matches_rejects_invalid_title_chars_top_bit(self):
        """Test that title with top-bit-set chars is rejected."""
        buffer = bytearray(102400)
        buffer[0:8] = b"TEST\x80ISC"  # Byte 4 has top bit set
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

        assert AcornDFSCatalogue.matches(surface) == False

    def test_matches_rejects_invalid_title_chars_control(self):
        """Test that title with control characters is rejected."""
        buffer = bytearray(102400)
        buffer[0:8] = b"TEST\x01ISC"  # Byte 4 is control char (1)
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

        assert AcornDFSCatalogue.matches(surface) == False

    def test_matches_accepts_null_padding_in_title(self):
        """Test that null bytes in title are accepted (padding)."""
        buffer = bytearray(102400)
        buffer[0:8] = b"TEST\x00\x00\x00\x00"  # Null padding
        buffer[256:260] = b"\x00\x00\x00\x00"  # Null padding
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

        assert AcornDFSCatalogue.matches(surface) == True

    def test_matches_rejects_invalid_num_files_byte(self):
        """Test that invalid num_files byte (not multiple of 8) is rejected."""
        buffer = bytearray(102400)
        buffer[0:8] = b"TESTDISC"
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 7  # Not a multiple of 8 (bits 0,1,2 set)
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

        assert AcornDFSCatalogue.matches(surface) == False

    def test_matches_rejects_invalid_boot_sectors_byte(self):
        """Test that invalid boot/sectors byte (bits 2,3,6,7 set) is rejected."""
        buffer = bytearray(102400)
        buffer[0:8] = b"TESTDISC"
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x04  # Bit 2 set (invalid)
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

        assert AcornDFSCatalogue.matches(surface) == False

    def test_matches_rejects_sectors_not_divisible_by_10(self):
        """Test that sector count not divisible by 10 is rejected."""
        buffer = bytearray(102400)
        buffer[0:8] = b"TESTDISC"
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 199  # Not divisible by 10

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        assert AcornDFSCatalogue.matches(surface) == False

    def test_matches_rejects_zero_tracks(self):
        """Test that zero tracks is rejected."""
        buffer = bytearray(102400)
        buffer[0:8] = b"TESTDISC"
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 0  # 0 sectors = 0 tracks (invalid)

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        assert AcornDFSCatalogue.matches(surface) == False

    def test_matches_accepts_80_tracks(self):
        """Test that 80-track discs are accepted."""
        buffer = bytearray(204800)  # 80 tracks * 10 sectors * 256 bytes
        buffer[0:8] = b"TESTDISC"
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x03  # High bits = 3
        buffer[263] = 32  # Low byte = 32, total = 800 sectors

        spec = SurfaceSpec(
            num_tracks=80,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        assert AcornDFSCatalogue.matches(surface) == True

    def test_matches_rejects_too_few_sectors(self):
        """Test that surface with < 4 sectors is rejected."""
        buffer = bytearray(768)  # Only 3 sectors
        buffer[0:8] = b"TESTDISC"
        buffer[256:260] = b"    "

        spec = SurfaceSpec(
            num_tracks=1,
            sectors_per_track=3,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=768,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        assert AcornDFSCatalogue.matches(surface) == False

    def test_matches_rejects_sectors_exceeding_surface_size(self):
        """Test that claimed sectors exceeding surface size is rejected."""
        buffer = bytearray(102400)  # 400 sectors
        buffer[0:8] = b"TESTDISC"
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x01  # High bits = 1
        buffer[263] = 244  # Low byte = 244, total = 500 sectors (exceeds 400)

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        assert AcornDFSCatalogue.matches(surface) == False

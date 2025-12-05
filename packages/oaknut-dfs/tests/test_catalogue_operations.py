"""Tests for Catalogue metadata operations (set_title, lock, rename, etc.)."""

import pytest

from oaknut_dfs.acorn_dfs_catalogue import AcornDFSCatalogue
from oaknut_dfs.surface import DiscImage, SurfaceSpec


class TestSetTitle:
    """Tests for set_title()."""

    def test_set_title_basic(self):
        """Test setting disk title."""
        buffer = bytearray(102400)

        # Initialize with title "OLDTITLE"
        buffer[0:8] = b"OLDTITLE"
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

        # Set new title
        catalogue.set_title("NEW DISK")

        # Verify title changed
        info = catalogue.get_disk_info()
        assert info.title == "NEW DISK"
        assert info.cycle_number == 1  # Cycle incremented

    def test_set_title_truncates(self):
        """Test that long titles are truncated to 12 chars."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 5
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

        # Set title longer than 12 chars
        catalogue.set_title("THIS IS TOO LONG")

        info = catalogue.get_disk_info()
        assert info.title == "THIS IS TOO"  # Truncated to 12, trailing spaces stripped
        assert info.cycle_number == 6  # Incremented


class TestSetBootOption:
    """Tests for set_boot_option()."""

    def test_set_boot_option(self):
        """Test setting boot option."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
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
        catalogue = AcornDFSCatalogue(surface)

        # Verify initial boot option
        assert catalogue.get_disk_info().boot_option == 1

        # Change to boot option 3
        catalogue.set_boot_option(3)

        info = catalogue.get_disk_info()
        assert info.boot_option == 3
        assert info.cycle_number == 1  # Incremented

    def test_set_boot_option_invalid(self):
        """Test that invalid boot option raises error."""
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

        with pytest.raises(ValueError, match="Boot option must be 0-3"):
            catalogue.set_boot_option(4)

        with pytest.raises(ValueError, match="Boot option must be 0-3"):
            catalogue.set_boot_option(-1)


class TestLockUnlockFile:
    """Tests for lock_file() and unlock_file()."""

    def test_lock_file(self):
        """Test locking a file."""
        buffer = bytearray(102400)

        # Create catalog with 1 unlocked file
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8  # 1 file
        buffer[262] = 0x00
        buffer[263] = 200

        # File: $.TEST (unlocked)
        buffer[8:15] = b"TEST   "
        buffer[15] = ord("$")  # Not locked (bit 7 clear)
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

        # Verify file is unlocked
        files = catalogue.list_files()
        assert files[0].locked == False

        # Lock the file
        catalogue.lock_file("$.TEST")

        # Verify file is now locked
        files = catalogue.list_files()
        assert files[0].locked == True
        assert catalogue.get_disk_info().cycle_number == 1  # Cycle incremented

    def test_unlock_file(self):
        """Test unlocking a file."""
        buffer = bytearray(102400)

        # Create catalog with 1 locked file
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8
        buffer[262] = 0x00
        buffer[263] = 200

        # File: $.TEST (locked)
        buffer[8:15] = b"TEST   "
        buffer[15] = ord("$") | 0x80  # Locked (bit 7 set)
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

        # Verify file is locked
        files = catalogue.list_files()
        assert files[0].locked == True

        # Unlock the file
        catalogue.unlock_file("$.TEST")

        # Verify file is now unlocked
        files = catalogue.list_files()
        assert files[0].locked == False
        assert catalogue.get_disk_info().cycle_number == 1

    def test_lock_nonexistent_file(self):
        """Test locking nonexistent file raises error."""
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

        with pytest.raises(FileNotFoundError):
            catalogue.lock_file("$.NOSUCHFILE")


class TestRenameFile:
    """Tests for rename_file()."""

    def test_rename_file_basic(self):
        """Test renaming a file."""
        buffer = bytearray(102400)

        # Create catalog with 1 file
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8
        buffer[262] = 0x00
        buffer[263] = 200

        # File: $.OLDNAME
        buffer[8:15] = b"OLDNAME"
        buffer[15] = ord("$")
        buffer[256 + 8:256 + 16] = bytes([0, 0x10, 0, 0x20, 100, 0, 0, 2])

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

        # Rename the file
        catalogue.rename_file("$.OLDNAME", "$.NEWNAME")

        # Verify new name
        files = catalogue.list_files()
        assert len(files) == 1
        assert files[0].filename == "NEWNAME"
        assert files[0].directory == "$"
        # Verify metadata preserved
        assert files[0].load_address == 0x1000
        assert files[0].exec_address == 0x2000
        assert files[0].length == 100
        assert files[0].start_sector == 2
        assert catalogue.get_disk_info().cycle_number == 1

    def test_rename_file_change_directory(self):
        """Test renaming file to different directory."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8
        buffer[262] = 0x00
        buffer[263] = 200

        # File: $.TEST
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
        catalogue = AcornDFSCatalogue(surface)

        # Rename to A.TEST
        catalogue.rename_file("$.TEST", "A.TEST")

        files = catalogue.list_files()
        assert files[0].filename == "TEST"
        assert files[0].directory == "A"

    def test_rename_preserves_locked_flag(self):
        """Test that rename preserves locked status."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8
        buffer[262] = 0x00
        buffer[263] = 200

        # File: $.TEST (locked)
        buffer[8:15] = b"TEST   "
        buffer[15] = ord("$") | 0x80  # Locked
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

        # Rename
        catalogue.rename_file("$.TEST", "$.RENAMED")

        # Verify locked status preserved
        files = catalogue.list_files()
        assert files[0].locked == True

    def test_rename_nonexistent_file(self):
        """Test renaming nonexistent file raises error."""
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

        with pytest.raises(FileNotFoundError):
            catalogue.rename_file("$.NOSUCHFILE", "$.NEWNAME")

    def test_rename_filename_too_long(self):
        """Test that too-long filename raises error."""
        buffer = bytearray(102400)

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
        catalogue = AcornDFSCatalogue(surface)

        with pytest.raises(ValueError, match="Filename too long"):
            catalogue.rename_file("$.TEST", "$.TOOLONGNAME")

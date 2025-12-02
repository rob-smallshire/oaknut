"""Tests for Layer 4: DFS Filesystem high-level interface."""

import pytest
from pathlib import Path

from oaknut_dfs.dfs_filesystem import (
    DFSFilesystem,
    BootOption,
    FileInfo,
    DiskInfo,
)
from oaknut_dfs.catalog import AcornDFSCatalog, FileEntry
from oaknut_dfs.catalog import DiskInfo as CatalogDiskInfo
from oaknut_dfs.sector_image import SSDSectorImage
from oaknut_dfs.disk_image import MemoryDiskImage


# ========== Fixtures ==========


@pytest.fixture
def empty_disk(tmp_path):
    """Create a minimal empty disk for testing."""
    # Create 40-track SSD (100KB)
    size = 40 * 10 * 256
    disk_image = MemoryDiskImage(size=size)
    sector_image = SSDSectorImage(disk_image)
    catalog = AcornDFSCatalog(sector_image)

    # Initialize catalog
    info = CatalogDiskInfo(
        title="TEST DISK",
        cycle_number=0,
        num_files=0,
        total_sectors=400,
        boot_option=0,
    )
    catalog.write_disk_info(info)

    # Save to tmp file
    disk_path = tmp_path / "test.ssd"
    data = disk_image.read_bytes(0, size)
    with open(disk_path, "wb") as f:
        f.write(data)

    return disk_path


@pytest.fixture
def disk_with_files(tmp_path):
    """Create a disk with several test files."""
    # Create empty disk
    size = 40 * 10 * 256
    disk_image = MemoryDiskImage(size=size)
    sector_image = SSDSectorImage(disk_image)
    catalog = AcornDFSCatalog(sector_image)

    # Initialize catalog
    info = CatalogDiskInfo(
        title="FILES",
        cycle_number=0,
        num_files=0,
        total_sectors=400,
        boot_option=0,
    )
    catalog.write_disk_info(info)

    # Add test files
    # File 1: $.HELLO - small text file
    hello_data = b"Hello, World!"
    sector_image.write_sector(2, hello_data.ljust(256, b"\x00"))
    catalog.add_file_entry(
        FileEntry(
            filename="HELLO  ",
            directory="$",
            locked=False,
            load_address=0x0000,
            exec_address=0x0000,
            length=len(hello_data),
            start_sector=2,
        )
    )

    # File 2: $.CODE - machine code file
    code_data = b"\x00\x01\x02\x03" * 100  # 400 bytes = 2 sectors
    sector_image.write_sector(3, code_data[0:256])
    sector_image.write_sector(4, code_data[256:400].ljust(256, b"\x00"))
    catalog.add_file_entry(
        FileEntry(
            filename="CODE   ",
            directory="$",
            locked=True,
            load_address=0x1900,
            exec_address=0x1900,
            length=len(code_data),
            start_sector=3,
        )
    )

    # File 3: A.DATA - different directory
    data = b"data" * 50  # 200 bytes = 1 sector
    sector_image.write_sector(5, data.ljust(256, b"\x00"))
    catalog.add_file_entry(
        FileEntry(
            filename="DATA   ",
            directory="A",
            locked=False,
            load_address=0x0000,
            exec_address=0x0000,
            length=len(data),
            start_sector=5,
        )
    )

    # Save to file
    disk_path = tmp_path / "files.ssd"
    data = disk_image.read_bytes(0, size)
    with open(disk_path, "wb") as f:
        f.write(data)

    return disk_path


# ========== Test DFSFilesystem.open() ==========


class TestDFSFilesystemOpen:
    """Test opening existing disk images."""

    def test_open_ssd_file_exists(self, empty_disk):
        """Can open an existing SSD file."""
        disk = DFSFilesystem.open(empty_disk)
        assert disk is not None
        assert disk._filepath == empty_disk

    def test_open_nonexistent_raises(self, tmp_path):
        """Opening nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            DFSFilesystem.open(tmp_path / "nonexistent.ssd")

    def test_open_detects_ssd_format(self, empty_disk):
        """Auto-detects SSD format from .ssd extension."""
        disk = DFSFilesystem.open(empty_disk)
        assert isinstance(disk._sector_image, SSDSectorImage)

    def test_open_with_path_string(self, empty_disk):
        """Can open using string path instead of Path object."""
        disk = DFSFilesystem.open(str(empty_disk))
        assert disk is not None

    def test_open_readonly_mode(self, empty_disk):
        """Can open in read-only mode."""
        disk = DFSFilesystem.open(empty_disk, writable=False)
        assert disk._filepath is None  # No path for read-only
        assert isinstance(disk._sector_image._disk_image, MemoryDiskImage)

    def test_open_writable_mode_default(self, empty_disk):
        """Writable mode is the default."""
        disk = DFSFilesystem.open(empty_disk)
        assert disk._filepath == empty_disk


# ========== Test DFSFilesystem.load() ==========


class TestDFSFilesystemLoad:
    """Test loading files from disk."""

    def test_load_existing_file(self, disk_with_files):
        """Can load an existing file."""
        disk = DFSFilesystem.open(disk_with_files)
        data = disk.load("$.HELLO")
        assert data == b"Hello, World!"

    def test_load_multi_sector_file(self, disk_with_files):
        """Can load file spanning multiple sectors."""
        disk = DFSFilesystem.open(disk_with_files)
        data = disk.load("$.CODE")
        expected = b"\x00\x01\x02\x03" * 100
        assert data == expected
        assert len(data) == 400

    def test_load_trims_padding(self, disk_with_files):
        """Load trims padding to exact file length."""
        disk = DFSFilesystem.open(disk_with_files)
        data = disk.load("$.HELLO")
        # File is 13 bytes, but stored in 256-byte sector
        assert len(data) == 13
        assert data == b"Hello, World!"

    def test_load_nonexistent_raises(self, disk_with_files):
        """Loading nonexistent file raises FileNotFoundError."""
        disk = DFSFilesystem.open(disk_with_files)
        with pytest.raises(FileNotFoundError, match="MISSING"):
            disk.load("$.MISSING")

    def test_load_different_directory(self, disk_with_files):
        """Can load file from different directory."""
        disk = DFSFilesystem.open(disk_with_files)
        data = disk.load("A.DATA")
        assert data == b"data" * 50

    def test_load_without_directory_uses_current(self, disk_with_files):
        """Load without directory prefix uses current directory."""
        disk = DFSFilesystem.open(disk_with_files)
        disk._current_directory = "$"
        data = disk.load("HELLO")  # No directory prefix
        assert data == b"Hello, World!"

    def test_load_error_message_includes_disk_path(self, disk_with_files):
        """Error message includes disk path when available."""
        disk = DFSFilesystem.open(disk_with_files)
        with pytest.raises(FileNotFoundError) as exc_info:
            disk.load("$.MISSING")
        assert "files.ssd" in str(exc_info.value)


# ========== Test DFSFilesystem.exists() ==========


class TestDFSFilesystemExists:
    """Test file existence checking."""

    def test_exists_returns_true_for_existing(self, disk_with_files):
        """exists() returns True for existing file."""
        disk = DFSFilesystem.open(disk_with_files)
        assert disk.exists("$.HELLO") is True

    def test_exists_returns_false_for_missing(self, disk_with_files):
        """exists() returns False for missing file."""
        disk = DFSFilesystem.open(disk_with_files)
        assert disk.exists("$.MISSING") is False

    def test_exists_works_without_directory(self, disk_with_files):
        """exists() works without directory prefix."""
        disk = DFSFilesystem.open(disk_with_files)
        disk._current_directory = "$"
        assert disk.exists("HELLO") is True

    def test_exists_different_directory(self, disk_with_files):
        """exists() works for files in different directories."""
        disk = DFSFilesystem.open(disk_with_files)
        assert disk.exists("A.DATA") is True


# ========== Test DFSFilesystem.get_file_info() ==========


class TestDFSFilesystemGetFileInfo:
    """Test getting file metadata."""

    def test_get_file_info_returns_fileinfo(self, disk_with_files):
        """get_file_info() returns FileInfo object."""
        disk = DFSFilesystem.open(disk_with_files)
        info = disk.get_file_info("$.HELLO")
        assert isinstance(info, FileInfo)

    def test_get_file_info_correct_metadata(self, disk_with_files):
        """get_file_info() returns correct metadata."""
        disk = DFSFilesystem.open(disk_with_files)
        info = disk.get_file_info("$.CODE")
        assert info.name == "$.CODE"
        assert info.filename == "CODE"
        assert info.directory == "$"
        assert info.locked is True
        assert info.load_address == 0x1900
        assert info.exec_address == 0x1900
        assert info.length == 400
        assert info.start_sector == 3

    def test_get_file_info_nonexistent_raises(self, disk_with_files):
        """get_file_info() raises for nonexistent file."""
        disk = DFSFilesystem.open(disk_with_files)
        with pytest.raises(FileNotFoundError):
            disk.get_file_info("$.MISSING")

    def test_fileinfo_sectors_property(self, disk_with_files):
        """FileInfo.sectors property calculates correctly."""
        disk = DFSFilesystem.open(disk_with_files)
        info = disk.get_file_info("$.HELLO")
        # 13 bytes = 1 sector
        assert info.sectors == 1

        info = disk.get_file_info("$.CODE")
        # 400 bytes = 2 sectors
        assert info.sectors == 2


# ========== Test DFSFilesystem.files property ==========


class TestDFSFilesystemFilesProperty:
    """Test the files property."""

    def test_files_returns_list(self, disk_with_files):
        """files property returns list of FileInfo."""
        disk = DFSFilesystem.open(disk_with_files)
        files = disk.files
        assert isinstance(files, list)
        assert len(files) == 3

    def test_files_all_are_fileinfo(self, disk_with_files):
        """All items in files list are FileInfo."""
        disk = DFSFilesystem.open(disk_with_files)
        for file in disk.files:
            assert isinstance(file, FileInfo)

    def test_files_empty_disk(self, empty_disk):
        """files property returns empty list for empty disk."""
        disk = DFSFilesystem.open(empty_disk)
        assert disk.files == []

    def test_files_contains_all_files(self, disk_with_files):
        """files property contains all files."""
        disk = DFSFilesystem.open(disk_with_files)
        names = {f.name for f in disk.files}
        assert names == {"$.HELLO", "$.CODE", "A.DATA"}


# ========== Test DFSFilesystem properties ==========


class TestDFSFilesystemProperties:
    """Test disk properties."""

    def test_title_property(self, disk_with_files):
        """title property returns disk title."""
        disk = DFSFilesystem.open(disk_with_files)
        assert disk.title == "FILES"

    def test_title_property_empty_disk(self, empty_disk):
        """title property works on empty disk."""
        disk = DFSFilesystem.open(empty_disk)
        assert disk.title == "TEST DISK"

    def test_free_sectors_empty_disk(self, empty_disk):
        """free_sectors property on empty disk."""
        disk = DFSFilesystem.open(empty_disk)
        # 400 total - 2 catalog = 398 free
        assert disk.free_sectors == 398

    def test_free_sectors_with_files(self, disk_with_files):
        """free_sectors property accounts for files."""
        disk = DFSFilesystem.open(disk_with_files)
        # 400 total - 2 catalog - 1 (HELLO) - 2 (CODE) - 1 (DATA) = 394
        assert disk.free_sectors == 394

    def test_info_property_returns_diskinfo(self, disk_with_files):
        """info property returns DiskInfo object."""
        disk = DFSFilesystem.open(disk_with_files)
        info = disk.info
        assert isinstance(info, DiskInfo)

    def test_info_property_correct_values(self, disk_with_files):
        """info property returns correct values."""
        disk = DFSFilesystem.open(disk_with_files)
        info = disk.info
        assert info.title == "FILES"
        assert info.num_files == 3
        assert info.total_sectors == 400
        assert info.free_sectors == 394
        assert info.boot_option == BootOption.NONE
        assert info.format == "SSD 40T"


# ========== Test magic methods ==========


class TestDFSFilesystemMagicMethods:
    """Test Python magic methods."""

    def test_contains_existing_file(self, disk_with_files):
        """__contains__ returns True for existing file."""
        disk = DFSFilesystem.open(disk_with_files)
        assert ("$.HELLO" in disk) is True

    def test_contains_missing_file(self, disk_with_files):
        """__contains__ returns False for missing file."""
        disk = DFSFilesystem.open(disk_with_files)
        assert ("$.MISSING" in disk) is False

    def test_iter_yields_fileinfo(self, disk_with_files):
        """__iter__ yields FileInfo objects."""
        disk = DFSFilesystem.open(disk_with_files)
        files = list(disk)
        assert len(files) == 3
        assert all(isinstance(f, FileInfo) for f in files)

    def test_iter_file_names(self, disk_with_files):
        """__iter__ yields all files."""
        disk = DFSFilesystem.open(disk_with_files)
        names = {f.name for f in disk}
        assert names == {"$.HELLO", "$.CODE", "A.DATA"}

    def test_len_returns_file_count(self, disk_with_files):
        """__len__ returns number of files."""
        disk = DFSFilesystem.open(disk_with_files)
        assert len(disk) == 3

    def test_len_empty_disk(self, empty_disk):
        """__len__ returns 0 for empty disk."""
        disk = DFSFilesystem.open(empty_disk)
        assert len(disk) == 0

    def test_repr_includes_info(self, disk_with_files):
        """__repr__ includes disk information."""
        disk = DFSFilesystem.open(disk_with_files)
        r = repr(disk)
        assert "DFSFilesystem" in r
        assert "FILES" in r
        assert "files=3" in r

    def test_str_readable(self, disk_with_files):
        """__str__ returns human-readable string."""
        disk = DFSFilesystem.open(disk_with_files)
        s = str(disk)
        assert "FILES" in s
        assert "3 files" in s
        assert "394 sectors free" in s


# ========== Test context manager ==========


class TestDFSFilesystemContextManager:
    """Test context manager functionality."""

    def test_context_manager_returns_self(self, empty_disk):
        """Context manager __enter__ returns self."""
        disk = DFSFilesystem.open(empty_disk)
        with disk as d:
            assert d is disk

    def test_context_manager_allows_operations(self, disk_with_files):
        """Can perform operations within context manager."""
        with DFSFilesystem.open(disk_with_files) as disk:
            data = disk.load("$.HELLO")
            assert data == b"Hello, World!"

    def test_context_manager_exits_cleanly(self, empty_disk):
        """Context manager exits without error."""
        with DFSFilesystem.open(empty_disk) as disk:
            _ = disk.title  # Do something

        # Should exit cleanly


# ========== Test format detection ==========


class TestFormatDetection:
    """Test format detection logic."""

    def test_detect_format_ssd_extension(self, tmp_path):
        """Detects SSD format from .ssd extension."""
        # Create minimal valid SSD file (40 tracks)
        path = tmp_path / "test.ssd"
        size = 40 * 10 * 256
        with open(path, "wb") as f:
            f.write(b"\x00" * size)

        fmt = DFSFilesystem._detect_format(path)
        assert fmt == "ssd"

    def test_detect_format_dsd_extension(self, tmp_path):
        """Detects DSD format from .dsd extension."""
        # Create minimal valid DSD file (40 tracks × 2 sides)
        path = tmp_path / "test.dsd"
        size = 40 * 2 * 10 * 256
        with open(path, "wb") as f:
            f.write(b"\x00" * size)

        fmt = DFSFilesystem._detect_format(path)
        assert fmt == "dsd-interleaved"

    def test_detect_format_invalid_size_raises(self, tmp_path):
        """Invalid size raises ValueError."""
        path = tmp_path / "test.ssd"
        with open(path, "wb") as f:
            f.write(b"\x00" * 1234)  # Not a multiple of 2560

        with pytest.raises(ValueError, match="Invalid disk image size"):
            DFSFilesystem._detect_format(path)

    def test_detect_format_unrecognized_size_raises(self, tmp_path):
        """Unrecognized but valid track count raises ValueError."""
        path = tmp_path / "test.img"
        size = 100 * 10 * 256  # 100 tracks - not standard
        with open(path, "wb") as f:
            f.write(b"\x00" * size)

        with pytest.raises(ValueError, match="Unrecognized disk size"):
            DFSFilesystem._detect_format(path)


# ========== Test helper methods ==========


class TestHelperMethods:
    """Test internal helper methods."""

    def test_resolve_filename_with_directory(self, empty_disk):
        """_resolve_filename preserves directory."""
        disk = DFSFilesystem.open(empty_disk)
        result = disk._resolve_filename("$.HELLO")
        assert result == "$.HELLO"

    def test_resolve_filename_without_directory(self, empty_disk):
        """_resolve_filename adds current directory."""
        disk = DFSFilesystem.open(empty_disk)
        disk._current_directory = "A"
        result = disk._resolve_filename("HELLO")
        assert result == "A.HELLO"

    def test_resolve_filename_uppercases(self, empty_disk):
        """_resolve_filename converts to uppercase."""
        disk = DFSFilesystem.open(empty_disk)
        result = disk._resolve_filename("$.hello")
        assert result == "$.HELLO"

    def test_entry_to_fileinfo_conversion(self):
        """_entry_to_fileinfo correctly converts FileEntry."""
        entry = FileEntry(
            filename="TEST   ",
            directory="$",
            locked=True,
            load_address=0x1900,
            exec_address=0x8000,
            length=1234,
            start_sector=10,
        )

        info = DFSFilesystem._entry_to_fileinfo(entry)

        assert info.name == "$.TEST"
        assert info.filename == "TEST"
        assert info.directory == "$"
        assert info.locked is True
        assert info.load_address == 0x1900
        assert info.exec_address == 0x8000
        assert info.length == 1234
        assert info.start_sector == 10


# ========== Test DFSFilesystem.create() ==========


class TestDFSFilesystemCreate:
    """Test creating new disk images."""

    def test_create_new_disk(self, tmp_path):
        """Can create a new disk image."""
        path = tmp_path / "new.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        assert disk is not None
        disk.close()
        assert path.exists()

    def test_create_with_title(self, tmp_path):
        """Created disk has specified title."""
        path = tmp_path / "new.ssd"
        disk = DFSFilesystem.create(path, title="MY DISK")
        assert disk.title == "MY DISK"

    def test_create_default_title_from_filename(self, tmp_path):
        """Default title derived from filename."""
        path = tmp_path / "game.ssd"
        disk = DFSFilesystem.create(path)
        assert disk.title == "GAME"

    def test_create_empty_catalog(self, tmp_path):
        """Created disk has empty catalog."""
        path = tmp_path / "new.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        assert len(disk.files) == 0

    def test_create_40_track_default(self, tmp_path):
        """Default is 40-track disk."""
        path = tmp_path / "new.ssd"
        disk = DFSFilesystem.create(path)
        info = disk.info
        assert info.total_sectors == 400  # 40 tracks * 10 sectors

    def test_create_80_track(self, tmp_path):
        """Can create 80-track disk."""
        path = tmp_path / "new.ssd"
        disk = DFSFilesystem.create(path, num_tracks=80)
        info = disk.info
        assert info.total_sectors == 800  # 80 tracks * 10 sectors

    def test_create_double_sided(self, tmp_path):
        """Can create double-sided disk."""
        path = tmp_path / "new.dsd"
        disk = DFSFilesystem.create(path, num_tracks=40, double_sided=True)
        info = disk.info
        assert info.total_sectors == 800  # 40 tracks * 2 sides * 10 sectors

    def test_create_existing_file_raises(self, tmp_path):
        """Creating over existing file raises FileExistsError."""
        path = tmp_path / "existing.ssd"
        path.write_bytes(b"existing data")

        with pytest.raises(FileExistsError):
            DFSFilesystem.create(path)

    def test_create_invalid_tracks_raises(self, tmp_path):
        """Invalid track count raises ValueError."""
        path = tmp_path / "new.ssd"
        with pytest.raises(ValueError, match="must be 40 or 80"):
            DFSFilesystem.create(path, num_tracks=100)

    def test_create_title_too_long_raises(self, tmp_path):
        """Title > 12 chars raises ValueError."""
        path = tmp_path / "new.ssd"
        with pytest.raises(ValueError, match="too long"):
            DFSFilesystem.create(path, title="VERY LONG TITLE")


# ========== Test DFSFilesystem.save() ==========


class TestDFSFilesystemSave:
    """Test saving files to disk."""

    def test_save_simple_file(self, tmp_path):
        """Can save a simple file."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        data = b"Hello, World!"
        disk.save("$.HELLO", data)

        assert disk.exists("$.HELLO")
        assert disk.load("$.HELLO") == data

    def test_save_with_load_address(self, tmp_path):
        """Can save with load address."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        data = b"\x00" * 100
        disk.save("$.CODE", data, load_address=0x1900)

        info = disk.get_file_info("$.CODE")
        assert info.load_address == 0x1900

    def test_save_with_exec_address(self, tmp_path):
        """Can save with exec address."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        data = b"\x00" * 100
        disk.save("$.CODE", data, exec_address=0x8000)

        info = disk.get_file_info("$.CODE")
        assert info.exec_address == 0x8000

    def test_save_locked_file(self, tmp_path):
        """Can save locked file."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.LOCKED", b"data", locked=True)

        info = disk.get_file_info("$.LOCKED")
        assert info.locked is True

    def test_save_multi_sector_file(self, tmp_path):
        """Can save file spanning multiple sectors."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        data = b"X" * 1000  # ~4 sectors
        disk.save("$.LARGE", data)

        assert disk.load("$.LARGE") == data

    def test_save_overwrite_default(self, tmp_path):
        """Save overwrites existing file by default."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE", b"old data")
        disk.save("$.FILE", b"new data")

        assert disk.load("$.FILE") == b"new data"

    def test_save_overwrite_false_raises(self, tmp_path):
        """Save with overwrite=False raises FileExistsError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE", b"old data")

        with pytest.raises(FileExistsError):
            disk.save("$.FILE", b"new data", overwrite=False)

    def test_save_locked_file_raises(self, tmp_path):
        """Cannot overwrite locked file."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.LOCKED", b"data", locked=True)

        with pytest.raises(PermissionError, match="locked"):
            disk.save("$.LOCKED", b"new data")

    def test_save_filename_too_long_raises(self, tmp_path):
        """Filename > 7 chars raises ValueError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        with pytest.raises(ValueError, match="too long"):
            disk.save("$.VERYLONGNAME", b"data")

    def test_save_disk_full_raises(self, tmp_path):
        """Saving when disk full raises ValueError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST", num_tracks=40)

        # Fill disk (398 free sectors - 2 for catalog)
        # Save a file too large to fit
        huge_data = b"X" * (399 * 256)

        with pytest.raises(ValueError, match="needs .* sectors"):
            disk.save("$.HUGE", huge_data)

    def test_save_round_trip(self, tmp_path):
        """Saved file can be loaded back."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        original = b"Test data " * 50
        disk.save("$.DATA", original)
        disk.close()

        # Reopen and load
        disk2 = DFSFilesystem.open(path)
        loaded = disk2.load("$.DATA")
        assert loaded == original

    def test_save_different_directory(self, tmp_path):
        """Can save files in different directories."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("A.FILE1", b"data1")
        disk.save("B.FILE2", b"data2")

        assert disk.exists("A.FILE1")
        assert disk.exists("B.FILE2")


# ========== Test DFSFilesystem.delete() ==========


class TestDFSFilesystemDelete:
    """Test deleting files."""

    def test_delete_existing_file(self, tmp_path):
        """Can delete an existing file."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE", b"data")
        disk.delete("$.FILE")

        assert not disk.exists("$.FILE")

    def test_delete_nonexistent_raises(self, tmp_path):
        """Deleting nonexistent file raises FileNotFoundError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        with pytest.raises(FileNotFoundError):
            disk.delete("$.MISSING")

    def test_delete_locked_file_raises(self, tmp_path):
        """Deleting locked file raises PermissionError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.LOCKED", b"data", locked=True)

        with pytest.raises(PermissionError, match="locked"):
            disk.delete("$.LOCKED")

    def test_delete_frees_sectors(self, tmp_path):
        """Deleting file frees sectors."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        free_before = disk.free_sectors
        disk.save("$.FILE", b"X" * 512)  # 2 sectors
        free_after_save = disk.free_sectors
        disk.delete("$.FILE")
        free_after_delete = disk.free_sectors

        assert free_after_save == free_before - 2
        assert free_after_delete == free_before


# ========== Test DFSFilesystem.rename() ==========


class TestDFSFilesystemRename:
    """Test renaming files."""

    def test_rename_file(self, tmp_path):
        """Can rename a file."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        data = b"test data"
        disk.save("$.OLD", data)
        disk.rename("$.OLD", "$.NEW")

        assert not disk.exists("$.OLD")
        assert disk.exists("$.NEW")
        assert disk.load("$.NEW") == data

    def test_rename_preserves_metadata(self, tmp_path):
        """Rename preserves file metadata."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.OLD", b"data", load_address=0x1900, exec_address=0x8000)

        old_info = disk.get_file_info("$.OLD")
        disk.rename("$.OLD", "$.NEW")
        new_info = disk.get_file_info("$.NEW")

        assert new_info.load_address == old_info.load_address
        assert new_info.exec_address == old_info.exec_address
        assert new_info.length == old_info.length

    def test_rename_to_different_directory(self, tmp_path):
        """Can rename to different directory."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE", b"data")
        disk.rename("$.FILE", "A.FILE")

        assert not disk.exists("$.FILE")
        assert disk.exists("A.FILE")

    def test_rename_nonexistent_raises(self, tmp_path):
        """Renaming nonexistent file raises FileNotFoundError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        with pytest.raises(FileNotFoundError):
            disk.rename("$.MISSING", "$.NEW")

    def test_rename_locked_file_raises(self, tmp_path):
        """Renaming locked file raises PermissionError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.LOCKED", b"data", locked=True)

        with pytest.raises(PermissionError, match="locked"):
            disk.rename("$.LOCKED", "$.NEW")

    def test_rename_to_existing_raises(self, tmp_path):
        """Renaming to existing filename raises FileExistsError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"data1")
        disk.save("$.FILE2", b"data2")

        with pytest.raises(FileExistsError):
            disk.rename("$.FILE1", "$.FILE2")

    def test_rename_filename_too_long_raises(self, tmp_path):
        """Rename to filename > 7 chars raises ValueError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.OLD", b"data")

        with pytest.raises(ValueError, match="too long"):
            disk.rename("$.OLD", "$.VERYLONGNAME")


# ========== Test lock/unlock ==========


class TestDFSFilesystemLockUnlock:
    """Test locking and unlocking files."""

    def test_lock_file(self, tmp_path):
        """Can lock a file."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE", b"data")
        disk.lock("$.FILE")

        info = disk.get_file_info("$.FILE")
        assert info.locked is True

    def test_unlock_file(self, tmp_path):
        """Can unlock a file."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE", b"data", locked=True)
        disk.unlock("$.FILE")

        info = disk.get_file_info("$.FILE")
        assert info.locked is False

    def test_lock_nonexistent_raises(self, tmp_path):
        """Locking nonexistent file raises FileNotFoundError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        with pytest.raises(FileNotFoundError):
            disk.lock("$.MISSING")

    def test_unlock_nonexistent_raises(self, tmp_path):
        """Unlocking nonexistent file raises FileNotFoundError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        with pytest.raises(FileNotFoundError):
            disk.unlock("$.MISSING")

    def test_locked_file_cannot_be_deleted(self, tmp_path):
        """Locked file cannot be deleted."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.LOCKED", b"data", locked=True)

        with pytest.raises(PermissionError):
            disk.delete("$.LOCKED")

    def test_locked_file_can_be_read(self, tmp_path):
        """Locked file can still be read."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        data = b"protected data"
        disk.save("$.LOCKED", data, locked=True)

        loaded = disk.load("$.LOCKED")
        assert loaded == data


# ========== Test free space management ==========


class TestFreeSpaceManagement:
    """Test free space calculation and allocation."""

    def test_get_free_map_empty_disk(self, tmp_path):
        """Free map on empty disk."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        free_map = disk.get_free_map()

        # Should be one contiguous region from sector 2 to end
        assert len(free_map) == 1
        assert free_map[0] == (2, 398)

    def test_get_free_map_with_files(self, tmp_path):
        """Free map accounts for files."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"X" * 256)  # 1 sector at position 2
        disk.save("$.FILE2", b"Y" * 256)  # 1 sector at position 3

        free_map = disk.get_free_map()
        # Should be one region starting at sector 4
        assert free_map[0][0] == 4

    def test_get_free_map_with_gap(self, tmp_path):
        """Free map shows gaps from deleted files."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"X" * 256)
        disk.save("$.FILE2", b"Y" * 256)
        disk.save("$.FILE3", b"Z" * 256)
        disk.delete("$.FILE2")  # Creates gap at sector 3

        free_map = disk.get_free_map()
        # Should have gap at sector 3 and free space after sector 4
        assert len(free_map) >= 1

    def test_find_free_space_allocates_first_fit(self, tmp_path):
        """_find_free_space uses first-fit algorithm."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        # Create a gap
        disk.save("$.FILE1", b"X" * 256)
        disk.save("$.FILE2", b"Y" * 512)  # 2 sectors
        disk.delete("$.FILE1")  # Frees sector 2

        # Small file should fit in the gap
        start = disk._find_free_space(256)
        assert start == 2  # First available sector


# ========== Test disk properties (setters) ==========


class TestDiskPropertiesSetters:
    """Test disk property setters."""

    def test_set_title(self, tmp_path):
        """Can set disk title."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="OLD")
        disk.title = "NEW TITLE"

        assert disk.title == "NEW TITLE"

    def test_set_title_persists(self, tmp_path):
        """Title persists after close/reopen."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="OLD")
        disk.title = "NEW"
        disk.close()

        disk2 = DFSFilesystem.open(path)
        assert disk2.title == "NEW"

    def test_set_title_too_long_raises(self, tmp_path):
        """Setting title > 12 chars raises ValueError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        with pytest.raises(ValueError, match="too long"):
            disk.title = "VERY LONG TITLE"

    def test_set_boot_option_enum(self, tmp_path):
        """Can set boot option with enum."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.boot_option = BootOption.EXEC

        assert disk.boot_option == BootOption.EXEC

    def test_set_boot_option_int(self, tmp_path):
        """Can set boot option with int."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.boot_option = 2  # RUN

        assert disk.boot_option == BootOption.RUN

    def test_set_boot_option_persists(self, tmp_path):
        """Boot option persists after close/reopen."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.boot_option = BootOption.LOAD
        disk.close()

        disk2 = DFSFilesystem.open(path)
        assert disk2.boot_option == BootOption.LOAD

    def test_set_boot_option_invalid_raises(self, tmp_path):
        """Invalid boot option raises ValueError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        with pytest.raises(ValueError, match="must be 0-3"):
            disk.boot_option = 5

    def test_set_boot_option_chainable(self, tmp_path):
        """set_boot_option() returns self for chaining."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        result = disk.set_boot_option(BootOption.RUN)

        assert result is disk
        assert disk.boot_option == BootOption.RUN


# ========== Test directory operations ==========


class TestDirectoryOperations:
    """Test directory navigation and listing."""

    def test_change_directory(self, tmp_path):
        """Can change current directory."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.change_directory("A")

        assert disk.current_directory == "A"

    def test_change_directory_lowercase(self, tmp_path):
        """change_directory converts to uppercase."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.change_directory("a")

        assert disk.current_directory == "A"

    def test_change_directory_invalid_raises(self, tmp_path):
        """Invalid directory raises ValueError."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        with pytest.raises(ValueError, match="single character"):
            disk.change_directory("AB")

    def test_current_directory_default(self, tmp_path):
        """Default current directory is $."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        assert disk.current_directory == "$"

    def test_list_directory_default(self, tmp_path):
        """list_directory() uses current directory by default."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"data1")
        disk.save("A.FILE2", b"data2")

        # Current directory is $
        files = disk.list_directory()
        names = [f.name for f in files]
        assert names == ["$.FILE1"]

    def test_list_directory_specified(self, tmp_path):
        """list_directory() can list specific directory."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"data1")
        disk.save("A.FILE2", b"data2")
        disk.save("A.FILE3", b"data3")

        files = disk.list_directory("A")
        assert len(files) == 2
        names = {f.name for f in files}
        assert names == {"A.FILE2", "A.FILE3"}

    def test_list_directory_empty(self, tmp_path):
        """list_directory() returns empty list for empty directory."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"data1")

        files = disk.list_directory("A")
        assert files == []

    def test_list_directory_lowercase(self, tmp_path):
        """list_directory() handles lowercase input."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("A.FILE", b"data")

        files = disk.list_directory("a")
        assert len(files) == 1


# ========== Test validation ==========


class TestValidation:
    """Test disk validation."""

    def test_validate_empty_disk(self, tmp_path):
        """Empty disk validates successfully."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        errors = disk.validate()

        assert errors == []

    def test_validate_with_files(self, tmp_path):
        """Disk with files validates successfully."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"data1")
        disk.save("$.FILE2", b"data2")

        errors = disk.validate()
        assert errors == []

    def test_validate_detects_overlaps(self, tmp_path):
        """validate() detects overlapping files."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        # Manually create overlapping files by manipulating catalog
        # (This is contrived - normal operations won't create overlaps)
        disk.save("$.FILE1", b"X" * 256)
        disk.save("$.FILE2", b"Y" * 256)

        # Force FILE2 to overlap with FILE1 by manipulating catalog
        files = disk._catalog.list_files()
        if len(files) >= 2:
            # Change FILE2's start sector to overlap
            for entry in files:
                if entry.filename.strip() == "FILE2":
                    entry.start_sector = 2  # Same as FILE1

            # Rebuild catalog with overlapping entries
            catalog_info = disk._catalog.read_disk_info()
            catalog_info.num_files = 0
            disk._catalog.write_disk_info(catalog_info)

            for entry in files:
                disk._catalog.add_file_entry(entry)

            errors = disk.validate()
            # Should detect overlap
            assert any("overlap" in e.lower() for e in errors)

    def test_validate_returns_list(self, tmp_path):
        """validate() always returns a list."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        errors = disk.validate()

        assert isinstance(errors, list)


# ========== Test free_bytes property ==========


class TestFreeBytesProperty:
    """Test free_bytes property."""

    def test_free_bytes_empty_disk(self, tmp_path):
        """free_bytes on empty disk."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        # 398 free sectors * 256 bytes
        assert disk.free_bytes == 398 * 256

    def test_free_bytes_with_files(self, tmp_path):
        """free_bytes accounts for files."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE", b"X" * 512)  # 2 sectors

        expected = (398 - 2) * 256
        assert disk.free_bytes == expected


# ========== Test compact ==========


class TestCompact:
    """Test disk compaction (defragmentation)."""

    def test_compact_empty_disk(self, tmp_path):
        """Compacting empty disk is a no-op."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        files_moved = disk.compact()
        assert files_moved == 0

    def test_compact_no_gaps(self, tmp_path):
        """Compacting disk with no gaps is a no-op."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"X" * 256)
        disk.save("$.FILE2", b"Y" * 256)
        disk.save("$.FILE3", b"Z" * 256)

        files_moved = disk.compact()
        assert files_moved == 0

    def test_compact_moves_files(self, tmp_path):
        """Compacting moves files to eliminate gaps."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"X" * 256)
        disk.save("$.FILE2", b"Y" * 256)
        disk.save("$.FILE3", b"Z" * 256)
        disk.delete("$.FILE2")  # Creates gap at sector 3

        files_moved = disk.compact()
        assert files_moved >= 1

        # Verify files still exist and are correct
        assert disk.load("$.FILE1") == b"X" * 256
        assert disk.load("$.FILE3") == b"Z" * 256

        # Verify no gaps in free space
        free_map = disk.get_free_map()
        assert len(free_map) == 1

    def test_compact_with_locked_files_raises(self, tmp_path):
        """Cannot compact disk with locked files."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"X" * 256)
        disk.save("$.LOCKED", b"Y" * 256, locked=True)
        disk.delete("$.FILE1")

        with pytest.raises(PermissionError, match="locked"):
            disk.compact()

    def test_compact_increases_free_space(self, tmp_path):
        """Compact doesn't change free bytes but consolidates space."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"X" * 256)
        disk.save("$.FILE2", b"Y" * 256)
        disk.save("$.FILE3", b"Z" * 256)
        disk.delete("$.FILE2")

        free_before = disk.free_bytes
        disk.compact()
        free_after = disk.free_bytes

        # Free bytes should be the same
        assert free_before == free_after

    def test_compact_preserves_metadata(self, tmp_path):
        """Compact preserves file metadata."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.FILE1", b"X" * 256, load_address=0x1900, exec_address=0x8023)
        disk.save("$.FILE2", b"Y" * 256)
        disk.save("$.FILE3", b"Z" * 256, load_address=0x5000)
        disk.delete("$.FILE2")

        disk.compact()

        info = disk.get_file_info("$.FILE1")
        assert info.load_address == 0x1900
        assert info.exec_address == 0x8023

        info3 = disk.get_file_info("$.FILE3")
        assert info3.load_address == 0x5000


# ========== Test copy_file ==========


class TestCopyFile:
    """Test file copying within disk."""

    def test_copy_file_basic(self, tmp_path):
        """Can copy a file within the disk."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        data = b"test data"
        disk.save("$.SOURCE", data)

        disk.copy_file("$.SOURCE", "$.DEST")

        assert disk.load("$.DEST") == data
        assert disk.load("$.SOURCE") == data  # Original still exists

    def test_copy_file_preserves_metadata(self, tmp_path):
        """copy_file preserves load/exec addresses."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.SOURCE", b"data", load_address=0x1900, exec_address=0x8023)

        disk.copy_file("$.SOURCE", "$.DEST")

        source_info = disk.get_file_info("$.SOURCE")
        dest_info = disk.get_file_info("$.DEST")

        assert dest_info.load_address == source_info.load_address
        assert dest_info.exec_address == source_info.exec_address

    def test_copy_file_preserves_locked(self, tmp_path):
        """copy_file preserves locked flag."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.SOURCE", b"data", locked=True)

        disk.copy_file("$.SOURCE", "$.DEST")

        dest_info = disk.get_file_info("$.DEST")
        assert dest_info.locked is True

    def test_copy_file_source_not_found(self, tmp_path):
        """copy_file raises if source doesn't exist."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        with pytest.raises(FileNotFoundError):
            disk.copy_file("$.MISSING", "$.DEST")

    def test_copy_file_dest_exists(self, tmp_path):
        """copy_file overwrites destination by default."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.SOURCE", b"new data")
        disk.save("$.DEST", b"old data")

        disk.copy_file("$.SOURCE", "$.DEST")

        assert disk.load("$.DEST") == b"new data"

    def test_copy_file_across_directories(self, tmp_path):
        """Can copy file to different directory."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        disk.save("$.SOURCE", b"data")

        disk.copy_file("$.SOURCE", "A.DEST")

        assert disk.load("A.DEST") == b"data"


# ========== Test save_text ==========


class TestSaveText:
    """Test text file saving convenience method."""

    def test_save_text_basic(self, tmp_path):
        """save_text saves text as bytes."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        disk.save_text("$.HELLO", "Hello World")

        assert disk.load("$.HELLO") == b"Hello World"

    def test_save_text_with_encoding(self, tmp_path):
        """save_text respects encoding parameter."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        disk.save_text("$.TEXT", "Hello", encoding="utf-8")

        assert disk.load("$.TEXT") == b"Hello"

    def test_save_text_with_metadata(self, tmp_path):
        """save_text accepts save kwargs."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")

        disk.save_text("$.TEXT", "Hello", load_address=0x1900, exec_address=0x8023)

        info = disk.get_file_info("$.TEXT")
        assert info.load_address == 0x1900
        assert info.exec_address == 0x8023

    def test_save_text_multiline(self, tmp_path):
        """save_text handles multiline text."""
        path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(path, title="TEST")
        text = "Line 1\nLine 2\nLine 3"

        disk.save_text("$.TEXT", text)

        loaded = disk.load("$.TEXT")
        assert loaded == text.encode("utf-8")


# ========== Test save_from_file ==========


class TestSaveFromFile:
    """Test importing files from host filesystem."""

    def test_save_from_file_basic(self, tmp_path):
        """save_from_file imports file from host."""
        source = tmp_path / "source.bin"
        data = b"test data"
        source.write_bytes(data)

        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        disk.save_from_file("$.FILE", source)

        assert disk.load("$.FILE") == data

    def test_save_from_file_with_path_object(self, tmp_path):
        """save_from_file accepts Path objects."""
        source = tmp_path / "source.bin"
        source.write_bytes(b"data")

        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        disk.save_from_file("$.FILE", Path(source))

        assert disk.exists("$.FILE")

    def test_save_from_file_with_string(self, tmp_path):
        """save_from_file accepts string paths."""
        source = tmp_path / "source.bin"
        source.write_bytes(b"data")

        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        disk.save_from_file("$.FILE", str(source))

        assert disk.exists("$.FILE")

    def test_save_from_file_with_metadata(self, tmp_path):
        """save_from_file accepts save kwargs."""
        source = tmp_path / "source.bin"
        source.write_bytes(b"data")

        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        disk.save_from_file("$.FILE", source, load_address=0x1900, locked=True)

        info = disk.get_file_info("$.FILE")
        assert info.load_address == 0x1900
        assert info.locked is True

    def test_save_from_file_not_found(self, tmp_path):
        """save_from_file raises if source doesn't exist."""
        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        with pytest.raises(FileNotFoundError):
            disk.save_from_file("$.FILE", tmp_path / "missing.bin")

    def test_save_from_file_large_file(self, tmp_path):
        """save_from_file handles larger files."""
        source = tmp_path / "large.bin"
        data = b"X" * 10000
        source.write_bytes(data)

        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        disk.save_from_file("$.LARGE", source)

        assert disk.load("$.LARGE") == data


# ========== Test export_all ==========


class TestExportAll:
    """Test exporting all files to host filesystem."""

    def test_export_all_basic(self, tmp_path):
        """export_all exports all files."""
        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")
        disk.save("$.FILE1", b"data1")
        disk.save("$.FILE2", b"data2")

        export_dir = tmp_path / "export"
        disk.export_all(export_dir)

        assert (export_dir / "$.FILE1").exists()
        assert (export_dir / "$.FILE2").exists()
        assert (export_dir / "$.FILE1").read_bytes() == b"data1"
        assert (export_dir / "$.FILE2").read_bytes() == b"data2"

    def test_export_all_creates_directory(self, tmp_path):
        """export_all creates target directory if needed."""
        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")
        disk.save("$.FILE", b"data")

        export_dir = tmp_path / "newdir" / "export"
        disk.export_all(export_dir)

        assert export_dir.exists()
        assert (export_dir / "$.FILE").exists()

    def test_export_all_with_inf_files(self, tmp_path):
        """export_all creates .inf metadata files."""
        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")
        disk.save("$.FILE", b"data", load_address=0x1900, exec_address=0x8023, locked=True)

        export_dir = tmp_path / "export"
        disk.export_all(export_dir, preserve_metadata=True)

        inf_file = export_dir / "$.FILE.inf"
        assert inf_file.exists()

        inf_content = inf_file.read_text()
        assert "$.FILE" in inf_content
        assert "1900" in inf_content
        assert "8023" in inf_content
        assert "Locked" in inf_content

    def test_export_all_without_inf_files(self, tmp_path):
        """export_all can skip .inf files."""
        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")
        disk.save("$.FILE", b"data", load_address=0x1900)

        export_dir = tmp_path / "export"
        disk.export_all(export_dir, preserve_metadata=False)

        assert (export_dir / "$.FILE").exists()
        assert not (export_dir / "$.FILE.inf").exists()

    def test_export_all_empty_disk(self, tmp_path):
        """export_all handles empty disk."""
        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        export_dir = tmp_path / "export"
        disk.export_all(export_dir)

        assert export_dir.exists()
        # No files should be created
        assert len(list(export_dir.iterdir())) == 0

    def test_export_all_multiple_directories(self, tmp_path):
        """export_all handles files from multiple directories."""
        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")
        disk.save("$.FILE1", b"data1")
        disk.save("A.FILE2", b"data2")
        disk.save("B.FILE3", b"data3")

        export_dir = tmp_path / "export"
        disk.export_all(export_dir)

        assert (export_dir / "$.FILE1").exists()
        assert (export_dir / "A.FILE2").exists()
        assert (export_dir / "B.FILE3").exists()


# ========== Test import_from_inf ==========


class TestImportFromInf:
    """Test importing files with .inf metadata."""

    def test_import_from_inf_with_inf_file(self, tmp_path):
        """import_from_inf uses .inf file when present."""
        data_file = tmp_path / "GAME"
        data_file.write_bytes(b"game data")

        inf_file = tmp_path / "GAME.inf"
        inf_file.write_text("$.GAME   FFFF1900 FFFF8023 000009 Locked")

        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        disk.import_from_inf(data_file)

        info = disk.get_file_info("$.GAME")
        assert info.load_address == 0xFFFF1900
        assert info.exec_address == 0xFFFF8023
        assert info.locked is True

    def test_import_from_inf_explicit_inf(self, tmp_path):
        """import_from_inf accepts explicit .inf path."""
        data_file = tmp_path / "GAME"
        data_file.write_bytes(b"game data")

        inf_file = tmp_path / "metadata.inf"
        inf_file.write_text("$.GAME   00001900 00008023 000009")

        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        disk.import_from_inf(data_file, inf_file)

        info = disk.get_file_info("$.GAME")
        assert info.load_address == 0x1900
        assert info.exec_address == 0x8023

    def test_import_from_inf_without_inf(self, tmp_path):
        """import_from_inf generates default metadata without .inf."""
        data_file = tmp_path / "GAME"
        data_file.write_bytes(b"game data")

        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        disk.import_from_inf(data_file)

        # Should create file with filename from data file
        info = disk.get_file_info("$.GAME")
        assert info.load_address == 0
        assert info.exec_address == 0
        assert info.locked is False

    def test_import_from_inf_preserves_data(self, tmp_path):
        """import_from_inf correctly imports data."""
        data_file = tmp_path / "GAME"
        data = b"game data content"
        data_file.write_bytes(data)

        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        disk.import_from_inf(data_file)

        assert disk.load("$.GAME") == data

    def test_import_from_inf_data_not_found(self, tmp_path):
        """import_from_inf raises if data file missing."""
        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        with pytest.raises(FileNotFoundError):
            disk.import_from_inf(tmp_path / "missing")

    def test_import_from_inf_parses_addresses(self, tmp_path):
        """import_from_inf correctly parses hex addresses."""
        data_file = tmp_path / "CODE"
        data_file.write_bytes(b"code")

        inf_file = tmp_path / "CODE.inf"
        inf_file.write_text("$.CODE   FFFF0E00 FFFF0E00 000004")

        disk_path = tmp_path / "test.ssd"
        disk = DFSFilesystem.create(disk_path, title="TEST")

        disk.import_from_inf(data_file)

        info = disk.get_file_info("$.CODE")
        assert info.load_address == 0xFFFF0E00
        assert info.exec_address == 0xFFFF0E00


# ========== Test create_from_files ==========


class TestCreateFromFiles:
    """Test builder pattern for creating populated disks."""

    def test_create_from_files_basic(self, tmp_path):
        """create_from_files creates and populates disk."""
        disk_path = tmp_path / "test.ssd"

        files = {
            "$.FILE1": b"data1",
            "$.FILE2": b"data2",
        }

        disk = DFSFilesystem.create_from_files(disk_path, files, title="TEST")

        assert disk.load("$.FILE1") == b"data1"
        assert disk.load("$.FILE2") == b"data2"
        assert disk.title == "TEST"

    def test_create_from_files_with_metadata(self, tmp_path):
        """create_from_files accepts file metadata."""
        disk_path = tmp_path / "test.ssd"

        files = {
            "$.GAME": {
                "data": b"game data",
                "load_address": 0x1900,
                "exec_address": 0x8023,
                "locked": True,
            },
        }

        disk = DFSFilesystem.create_from_files(disk_path, files)

        info = disk.get_file_info("$.GAME")
        assert info.load_address == 0x1900
        assert info.exec_address == 0x8023
        assert info.locked is True

    def test_create_from_files_mixed_format(self, tmp_path):
        """create_from_files accepts mixed bytes and dict."""
        disk_path = tmp_path / "test.ssd"

        files = {
            "$.FILE1": b"simple data",
            "$.FILE2": {
                "data": b"complex data",
                "load_address": 0x1900,
            },
        }

        disk = DFSFilesystem.create_from_files(disk_path, files)

        assert disk.load("$.FILE1") == b"simple data"
        assert disk.load("$.FILE2") == b"complex data"

        info2 = disk.get_file_info("$.FILE2")
        assert info2.load_address == 0x1900

    def test_create_from_files_with_create_kwargs(self, tmp_path):
        """create_from_files passes kwargs to create()."""
        disk_path = tmp_path / "test.ssd"

        files = {"$.FILE": b"data"}

        disk = DFSFilesystem.create_from_files(
            disk_path, files, title="MYTEST", num_tracks=80
        )

        assert disk.title == "MYTEST"
        # Should have more sectors with 80 tracks
        assert disk.info.total_sectors > 400

    def test_create_from_files_empty(self, tmp_path):
        """create_from_files handles empty file dict."""
        disk_path = tmp_path / "test.ssd"

        disk = DFSFilesystem.create_from_files(disk_path, {}, title="EMPTY")

        assert disk.title == "EMPTY"
        assert len(disk.files) == 0

    def test_create_from_files_returns_disk(self, tmp_path):
        """create_from_files returns DFSFilesystem instance."""
        disk_path = tmp_path / "test.ssd"

        files = {"$.FILE": b"data"}
        disk = DFSFilesystem.create_from_files(disk_path, files)

        assert isinstance(disk, DFSFilesystem)
        assert disk.exists("$.FILE")

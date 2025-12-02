"""Tests for Layer 3: Catalog management."""

import pytest
from oaknut_dfs.disk_image import MemoryDiskImage
from oaknut_dfs.sector_image import SSDSectorImage
from oaknut_dfs.catalog import (
    Catalog,
    AcornDFSCatalog,
    FileEntry,
    DiskInfo,
)
from oaknut_dfs.exceptions import CatalogFullError, FileExistsError, FileLocked


class TestFileEntry:
    """Tests for FileEntry dataclass."""

    def test_full_name(self):
        """Full name combines directory and filename."""
        entry = FileEntry(
            filename="HELLO",
            directory="$",
            locked=False,
            load_address=0x1900,
            exec_address=0x1900,
            length=100,
            start_sector=2,
        )
        assert entry.full_name == "$.HELLO"

    def test_full_name_with_spaces(self):
        """Full name strips trailing spaces from filename."""
        entry = FileEntry(
            filename="HI     ",
            directory="A",
            locked=False,
            load_address=0,
            exec_address=0,
            length=50,
            start_sector=2,
        )
        assert entry.full_name == "A.HI"

    def test_sectors_required_exact(self):
        """File requiring exact sectors."""
        entry = FileEntry(
            filename="TEST",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=256,
            start_sector=2,
        )
        assert entry.sectors_required == 1

    def test_sectors_required_partial(self):
        """File requiring partial sector rounds up."""
        entry = FileEntry(
            filename="TEST",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=257,
            start_sector=2,
        )
        assert entry.sectors_required == 2

    def test_sectors_required_zero(self):
        """Zero-length file requires 0 sectors."""
        entry = FileEntry(
            filename="EMPTY",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=0,
            start_sector=2,
        )
        assert entry.sectors_required == 0


class TestAcornDFSCatalog:
    """Tests for Acorn DFS catalog implementation."""

    @pytest.fixture
    def empty_disk(self):
        """Create an empty formatted disk."""
        disk = MemoryDiskImage(size=102400)  # 400 sectors
        sector_img = SSDSectorImage(disk)
        catalog = AcornDFSCatalog(sector_img)

        # Initialize with empty catalog
        info = DiskInfo(
            title="EMPTY",
            cycle_number=0,
            num_files=0,
            total_sectors=400,
            boot_option=0,
        )
        catalog.write_disk_info(info)

        return catalog

    def test_read_disk_info_empty(self, empty_disk):
        """Read disk info from empty disk."""
        info = empty_disk.read_disk_info()
        assert info.title == "EMPTY"
        assert info.cycle_number == 0
        assert info.num_files == 0
        assert info.total_sectors == 400
        assert info.boot_option == 0

    def test_write_disk_info(self, empty_disk):
        """Write disk info and read it back."""
        new_info = DiskInfo(
            title="NEW DISK",
            cycle_number=5,
            num_files=0,
            total_sectors=400,
            boot_option=2,
        )
        empty_disk.write_disk_info(new_info)

        read_info = empty_disk.read_disk_info()
        assert read_info.title == "NEW DISK"
        assert read_info.cycle_number == 5
        assert read_info.num_files == 0
        assert read_info.total_sectors == 400
        assert read_info.boot_option == 2

    def test_write_disk_info_long_title(self, empty_disk):
        """Long titles are truncated to 12 characters."""
        info = DiskInfo(
            title="THIS IS A VERY LONG TITLE",
            cycle_number=0,
            num_files=0,
            total_sectors=400,
            boot_option=0,
        )
        empty_disk.write_disk_info(info)

        read_info = empty_disk.read_disk_info()
        assert len(read_info.title) <= 12
        assert read_info.title == "THIS IS A VE"

    def test_write_disk_info_short_title(self, empty_disk):
        """Short titles are padded."""
        info = DiskInfo(
            title="HI",
            cycle_number=0,
            num_files=0,
            total_sectors=400,
            boot_option=0,
        )
        empty_disk.write_disk_info(info)

        read_info = empty_disk.read_disk_info()
        assert read_info.title == "HI"  # Trailing spaces stripped on read

    def test_list_files_empty(self, empty_disk):
        """List files on empty disk returns empty list."""
        files = empty_disk.list_files()
        assert files == []

    def test_add_file_entry(self, empty_disk):
        """Add a single file entry."""
        entry = FileEntry(
            filename="HELLO",
            directory="$",
            locked=False,
            load_address=0x1900,
            exec_address=0x1900,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        files = empty_disk.list_files()
        assert len(files) == 1
        assert files[0].full_name == "$.HELLO"
        assert files[0].load_address == 0x1900
        assert files[0].exec_address == 0x1900
        assert files[0].length == 100
        assert files[0].start_sector == 2
        assert files[0].locked is False

    def test_add_file_entry_locked(self, empty_disk):
        """Add a locked file entry."""
        entry = FileEntry(
            filename="SECRET",
            directory="$",
            locked=True,
            load_address=0x2000,
            exec_address=0x2000,
            length=200,
            start_sector=5,
        )
        empty_disk.add_file_entry(entry)

        files = empty_disk.list_files()
        assert len(files) == 1
        assert files[0].locked is True

    def test_add_multiple_files(self, empty_disk):
        """Add multiple file entries."""
        for i in range(5):
            entry = FileEntry(
                filename=f"FILE{i}",
                directory="$",
                locked=False,
                load_address=0x1900 + i * 100,
                exec_address=0x1900 + i * 100,
                length=100 + i * 10,
                start_sector=2 + i * 2,
            )
            empty_disk.add_file_entry(entry)

        files = empty_disk.list_files()
        assert len(files) == 5
        for i in range(5):
            assert files[i].full_name == f"$.FILE{i}"
            assert files[i].length == 100 + i * 10

    def test_add_file_different_directory(self, empty_disk):
        """Add files in different directories."""
        entry1 = FileEntry(
            filename="DATA",
            directory="$",
            locked=False,
            load_address=0x1900,
            exec_address=0x1900,
            length=100,
            start_sector=2,
        )
        entry2 = FileEntry(
            filename="DATA",
            directory="A",
            locked=False,
            load_address=0x2000,
            exec_address=0x2000,
            length=200,
            start_sector=5,
        )
        empty_disk.add_file_entry(entry1)
        empty_disk.add_file_entry(entry2)

        files = empty_disk.list_files()
        assert len(files) == 2
        assert files[0].full_name == "$.DATA"
        assert files[1].full_name == "A.DATA"

    def test_add_file_increments_cycle(self, empty_disk):
        """Adding file increments cycle number."""
        initial_info = empty_disk.read_disk_info()
        initial_cycle = initial_info.cycle_number

        entry = FileEntry(
            filename="TEST",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        new_info = empty_disk.read_disk_info()
        assert new_info.cycle_number == (initial_cycle + 1) % 256

    def test_add_file_updates_num_files(self, empty_disk):
        """Adding file updates num_files count."""
        entry = FileEntry(
            filename="TEST",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        info = empty_disk.read_disk_info()
        assert info.num_files == 1

    def test_add_file_duplicate_raises(self, empty_disk):
        """Adding duplicate filename raises FileExistsError."""
        entry = FileEntry(
            filename="DUPE",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        with pytest.raises(FileExistsError, match="already exists"):
            empty_disk.add_file_entry(entry)

    def test_add_file_filename_too_long_raises(self, empty_disk):
        """Filename longer than 7 characters raises ValueError."""
        entry = FileEntry(
            filename="TOOLONG1",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=2,
        )
        with pytest.raises(ValueError, match="too long"):
            empty_disk.add_file_entry(entry)

    def test_add_file_catalog_full_raises(self, empty_disk):
        """Adding more than MAX_FILES raises CatalogFullError."""
        # Add MAX_FILES files
        for i in range(AcornDFSCatalog.MAX_FILES):
            entry = FileEntry(
                filename=f"F{i:02d}",
                directory="$",
                locked=False,
                load_address=0,
                exec_address=0,
                length=100,
                start_sector=2 + i * 2,
            )
            empty_disk.add_file_entry(entry)

        # Try to add one more
        entry = FileEntry(
            filename="EXTRA",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=100,
        )
        with pytest.raises(CatalogFullError, match="Catalog is full"):
            empty_disk.add_file_entry(entry)

    def test_find_file_exists(self, empty_disk):
        """Find an existing file."""
        entry = FileEntry(
            filename="FINDME",
            directory="$",
            locked=False,
            load_address=0x1900,
            exec_address=0x1900,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        found = empty_disk.find_file("$.FINDME")
        assert found is not None
        assert found.full_name == "$.FINDME"

    def test_find_file_case_insensitive(self, empty_disk):
        """File search is case-insensitive."""
        entry = FileEntry(
            filename="Hello",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        found = empty_disk.find_file("$.HELLO")
        assert found is not None
        assert found.full_name.upper() == "$.HELLO"

    def test_find_file_not_found(self, empty_disk):
        """Find non-existent file returns None."""
        found = empty_disk.find_file("$.NOTHERE")
        assert found is None

    def test_remove_file_entry(self, empty_disk):
        """Remove a file entry."""
        entry = FileEntry(
            filename="REMOVE",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        empty_disk.remove_file_entry("$.REMOVE")

        files = empty_disk.list_files()
        assert len(files) == 0

    def test_remove_file_from_middle(self, empty_disk):
        """Remove file from middle of catalog."""
        for i in range(3):
            entry = FileEntry(
                filename=f"FILE{i}",
                directory="$",
                locked=False,
                load_address=0,
                exec_address=0,
                length=100,
                start_sector=2 + i * 2,
            )
            empty_disk.add_file_entry(entry)

        empty_disk.remove_file_entry("$.FILE1")

        files = empty_disk.list_files()
        assert len(files) == 2
        assert files[0].full_name == "$.FILE0"
        assert files[1].full_name == "$.FILE2"

    def test_remove_file_not_found_raises(self, empty_disk):
        """Removing non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            empty_disk.remove_file_entry("$.NOTHERE")

    def test_remove_locked_file_raises(self, empty_disk):
        """Removing locked file raises FileLocked."""
        entry = FileEntry(
            filename="LOCKED",
            directory="$",
            locked=True,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        with pytest.raises(FileLocked, match="locked"):
            empty_disk.remove_file_entry("$.LOCKED")

    def test_remove_file_updates_num_files(self, empty_disk):
        """Removing file updates num_files count."""
        entry = FileEntry(
            filename="TEST",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)
        empty_disk.remove_file_entry("$.TEST")

        info = empty_disk.read_disk_info()
        assert info.num_files == 0

    def test_remove_file_increments_cycle(self, empty_disk):
        """Removing file increments cycle number."""
        entry = FileEntry(
            filename="TEST",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        info_before = empty_disk.read_disk_info()
        cycle_before = info_before.cycle_number

        empty_disk.remove_file_entry("$.TEST")

        info_after = empty_disk.read_disk_info()
        assert info_after.cycle_number == (cycle_before + 1) % 256

    def test_validate_empty_disk(self, empty_disk):
        """Empty disk validates successfully."""
        errors = empty_disk.validate()
        assert errors == []

    def test_validate_disk_with_files(self, empty_disk):
        """Disk with valid files validates successfully."""
        for i in range(3):
            entry = FileEntry(
                filename=f"FILE{i}",
                directory="$",
                locked=False,
                load_address=0x1900,
                exec_address=0x1900,
                length=100,
                start_sector=2 + i * 2,
            )
            empty_disk.add_file_entry(entry)

        errors = empty_disk.validate()
        assert errors == []

    def test_18bit_addresses(self, empty_disk):
        """Test 18-bit address handling."""
        entry = FileEntry(
            filename="BIG",
            directory="$",
            locked=False,
            load_address=0x20000,  # 18-bit address (bits 16-17 = 0b10, no sign extension)
            exec_address=0x10000,  # 18-bit address (bits 16-17 = 0b01, no sign extension)
            length=0x10000,  # 18-bit length
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        files = empty_disk.list_files()
        assert len(files) == 1
        assert files[0].load_address == 0x20000
        assert files[0].exec_address == 0x10000
        assert files[0].length == 0x10000

    def test_sign_extended_addresses(self, empty_disk):
        """Test sign extension for I/O processor addresses."""
        # Address 0x3FFFF with sign extension becomes 0xFFFFFFFF
        entry = FileEntry(
            filename="IO",
            directory="$",
            locked=False,
            load_address=0xFFFFFFFF,  # Will be encoded as 0x3FFFF with sign bit
            exec_address=0xFFFF0000,
            length=100,
            start_sector=2,
        )
        empty_disk.add_file_entry(entry)

        files = empty_disk.list_files()
        assert len(files) == 1
        # Should read back with sign extension
        assert files[0].load_address == 0xFFFFFFFF
        assert files[0].exec_address == 0xFFFF0000

    def test_10bit_sector_numbers(self, empty_disk):
        """Test 10-bit sector number handling."""
        entry = FileEntry(
            filename="FAR",
            directory="$",
            locked=False,
            load_address=0,
            exec_address=0,
            length=100,
            start_sector=1000,  # 10-bit: requires high bits
        )
        empty_disk.add_file_entry(entry)

        files = empty_disk.list_files()
        assert len(files) == 1
        assert files[0].start_sector == 1000

    def test_all_boot_options(self, empty_disk):
        """Test all boot options (0-3)."""
        for boot_opt in [0, 1, 2, 3]:
            info = DiskInfo(
                title="TEST",
                cycle_number=0,
                num_files=0,
                total_sectors=400,
                boot_option=boot_opt,
            )
            empty_disk.write_disk_info(info)

            read_info = empty_disk.read_disk_info()
            assert read_info.boot_option == boot_opt

    def test_implements_catalog_interface(self, empty_disk):
        """AcornDFSCatalog implements Catalog interface."""
        assert isinstance(empty_disk, Catalog)

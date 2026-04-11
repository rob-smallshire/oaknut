"""Tests for ADFS disc image creation.

Parameterised round-trip tests: create an empty ADFS disc image, verify
the root directory is empty, the total size and free space match
expectations, and that files can be written and read back.
"""


import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S, ADFS_M, ADFS_L


# Expected properties for each ADFS format:
# (format_const, total_sectors, root_dir_sectors, free_space_map_sectors)
# Free space = (total_sectors - fsm_sectors - root_dir_sectors) * 256
ADFS_FORMATS = [
    pytest.param(
        ADFS_S,
        640,      # total sectors (40T × 16spt × 1 side)
        163840,   # total bytes
        id="adfs-s",
    ),
    pytest.param(
        ADFS_M,
        1280,     # total sectors (80T × 16spt × 1 side)
        327680,   # total bytes
        id="adfs-m",
    ),
    pytest.param(
        ADFS_L,
        2560,     # total sectors (80T × 16spt × 2 sides)
        655360,   # total bytes
        id="adfs-l",
    ),
]


class TestADFSCreateInMemory:
    """Test ADFS.create() for in-memory disc images."""

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_empty_root(self, adfs_format, expected_total_sectors, expected_total_bytes):
        adfs = ADFS.create(adfs_format)
        assert list(adfs.root) == []

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_total_size(self, adfs_format, expected_total_sectors, expected_total_bytes):
        adfs = ADFS.create(adfs_format)
        assert adfs.total_size == expected_total_bytes

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_free_space(self, adfs_format, expected_total_sectors, expected_total_bytes):
        adfs = ADFS.create(adfs_format)
        # Free space map (2 sectors) + root dir (5 sectors) = 7 sectors used
        expected_free = (expected_total_sectors - 7) * 256
        assert adfs.free_space == expected_free

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_default_title_is_empty(self, adfs_format, expected_total_sectors, expected_total_bytes):
        adfs = ADFS.create(adfs_format)
        assert adfs.title == ""

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_custom_title(self, adfs_format, expected_total_sectors, expected_total_bytes):
        adfs = ADFS.create(adfs_format, title="TestDisc")
        assert adfs.title == "TestDisc"

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_default_boot_option(self, adfs_format, expected_total_sectors, expected_total_bytes):
        adfs = ADFS.create(adfs_format)
        assert adfs.boot_option == 0

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_custom_boot_option(self, adfs_format, expected_total_sectors, expected_total_bytes):
        adfs = ADFS.create(adfs_format, boot_option=3)
        assert adfs.boot_option == 3

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_root_is_directory(self, adfs_format, expected_total_sectors, expected_total_bytes):
        adfs = ADFS.create(adfs_format)
        assert adfs.root.is_dir()
        assert adfs.root.exists()

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_validate_clean(self, adfs_format, expected_total_sectors, expected_total_bytes):
        adfs = ADFS.create(adfs_format)
        assert adfs.validate() == []

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_walk_empty(self, adfs_format, expected_total_sectors, expected_total_bytes):
        adfs = ADFS.create(adfs_format)
        results = list(adfs.root.walk())
        assert len(results) == 1
        dirpath, dirnames, filenames = results[0]
        assert str(dirpath) == "$"
        assert dirnames == []
        assert filenames == []


class TestADFSCreateRoundTrip:
    """Test writing files to created images and reading them back."""

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_create_and_reopen_from_buffer(self, adfs_format, expected_total_sectors, expected_total_bytes):
        """Create, write a file, then reopen from the same buffer."""
        adfs = ADFS.create(adfs_format)
        # Access the underlying buffer for reopening
        buffer = adfs._disc._disc_image.buffer
        adfs2 = ADFS.from_buffer(buffer)
        assert adfs2.title == ""
        assert list(adfs2.root) == []


class TestADFSCreateFile:
    """Test ADFS.create_file() for file-backed disc images."""

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_create_file_and_reopen(self, adfs_format, expected_total_sectors, expected_total_bytes, tmp_path):
        filepath = tmp_path / "test.adf"
        with ADFS.create_file(filepath, adfs_format, title="Persist") as adfs:
            pass

        with ADFS.from_file(filepath) as adfs:
            assert adfs.title == "Persist"
            assert list(adfs.root) == []

    @pytest.mark.parametrize("adfs_format,expected_total_sectors,expected_total_bytes", ADFS_FORMATS)
    def test_created_file_size(self, adfs_format, expected_total_sectors, expected_total_bytes, tmp_path):
        filepath = tmp_path / "test.adf"
        with ADFS.create_file(filepath, adfs_format):
            pass
        assert filepath.stat().st_size == expected_total_bytes

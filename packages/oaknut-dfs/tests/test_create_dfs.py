"""Tests for DFS disc image creation.

Parameterised round-trip tests: create an empty disc image, verify the
catalogue is empty, the total sectors and free space match expectations,
and that files can be written and read back.
"""


import pytest

from oaknut_dfs.dfs import DFS
from oaknut_dfs.formats import (
    ACORN_DFS_40T_SINGLE_SIDED,
    ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL,
    ACORN_DFS_80T_SINGLE_SIDED,
    ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL,
    WATFORD_DFS_40T_SINGLE_SIDED,
    WATFORD_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
    WATFORD_DFS_40T_DOUBLE_SIDED_SEQUENTIAL,
    WATFORD_DFS_80T_SINGLE_SIDED,
    WATFORD_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
    WATFORD_DFS_80T_DOUBLE_SIDED_SEQUENTIAL,
)


# Expected properties for each format:
# (format, label, tracks, sectors_per_track, num_sides, catalogue_sectors, catalogue_name)
ACORN_FORMATS = [
    pytest.param(ACORN_DFS_40T_SINGLE_SIDED, 400, 2, id="acorn-40t-ss"),
    pytest.param(ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, 400, 2, id="acorn-40t-dsi"),
    pytest.param(ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL, 400, 2, id="acorn-40t-dss"),
    pytest.param(ACORN_DFS_80T_SINGLE_SIDED, 800, 2, id="acorn-80t-ss"),
    pytest.param(ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, 800, 2, id="acorn-80t-dsi"),
    pytest.param(ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL, 800, 2, id="acorn-80t-dss"),
]

WATFORD_FORMATS = [
    pytest.param(WATFORD_DFS_40T_SINGLE_SIDED, 400, 4, id="watford-40t-ss"),
    pytest.param(WATFORD_DFS_40T_DOUBLE_SIDED_INTERLEAVED, 400, 4, id="watford-40t-dsi"),
    pytest.param(WATFORD_DFS_40T_DOUBLE_SIDED_SEQUENTIAL, 400, 4, id="watford-40t-dss"),
    pytest.param(WATFORD_DFS_80T_SINGLE_SIDED, 800, 4, id="watford-80t-ss"),
    pytest.param(WATFORD_DFS_80T_DOUBLE_SIDED_INTERLEAVED, 800, 4, id="watford-80t-dsi"),
    pytest.param(WATFORD_DFS_80T_DOUBLE_SIDED_SEQUENTIAL, 800, 4, id="watford-80t-dss"),
]

ALL_FORMATS = ACORN_FORMATS + WATFORD_FORMATS


class TestDFSCreateInMemory:
    """Test DFS.create() for in-memory disc images."""

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_empty_catalogue(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        assert len(dfs.files) == 0

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_total_sectors(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        disk_info = dfs._catalogued_surface.disk_info
        assert disk_info.total_sectors == expected_total_sectors

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_free_sectors(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        assert dfs.free_sectors == expected_total_sectors - catalogue_sectors

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_default_title_is_empty(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        assert dfs.title.strip("\x00 ") == ""

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_custom_title(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format, title="TestDisc")
        assert dfs.title.strip("\x00 ") == "TestDisc"

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_default_boot_option(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        assert dfs.boot_option == 0

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_custom_boot_option(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format, boot_option=3)
        assert dfs.boot_option == 3

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_root_is_empty(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        assert list(dfs.root) == []

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_validate_clean(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        assert dfs.validate() == []


class TestDFSCreateRoundTrip:
    """Test writing files to created images and reading them back."""

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_save_and_load(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        dfs.save("$.HELLO", b"Hello, World!", load_address=0x1900)
        assert len(dfs.files) == 1
        assert dfs.load("$.HELLO") == b"Hello, World!"

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_catalogue_high_bits_round_trip(self, disk_format, expected_total_sectors, catalogue_sectors):
        """Verify that the high bits (16-17) of load, exec, and length
        are packed and unpacked correctly in the catalogue extra byte.

        Regression test: the write path previously used wrong bit shifts
        (>> 14, >> 12, >> 10 instead of >> 16), causing values with
        non-zero bits 12-15 but zero bits 16-17 to be stored incorrectly.
        """
        dfs = DFS.create(disk_format)
        # 15053 bytes — bits 12-13 of length are non-zero, bits 16-17 are zero
        data = b"x" * 15053
        dfs.save("$.PROG", data, load_address=0x0800, exec_address=0x8023)
        entry = dfs.files[0]
        assert entry.length == 15053
        assert entry.load_address == 0x0800
        assert entry.exec_address == 0x8023
        assert dfs.load("$.PROG") == data

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_save_and_load_via_path(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        (dfs.root / "$" / "DATA").write_bytes(b"test data", load_address=0x2000)
        data = (dfs.root / "$" / "DATA").read_bytes()
        assert data == b"test data"

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_free_sectors_decrease_after_save(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        initial_free = dfs.free_sectors
        dfs.save("$.FILE", b"x" * 512)  # 2 sectors
        assert dfs.free_sectors == initial_free - 2

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_save_delete_roundtrip(self, disk_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disk_format)
        initial_free = dfs.free_sectors
        dfs.save("$.TEMP", b"temporary")
        dfs.delete("$.TEMP")
        assert len(dfs.files) == 0
        # Free sectors restored after compaction
        dfs.compact()
        assert dfs.free_sectors == initial_free


class TestDFSCreateFile:
    """Test DFS.create_file() for file-backed disc images."""

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_create_file_empty_and_reopen(self, disk_format, expected_total_sectors, catalogue_sectors, tmp_path):
        filepath = tmp_path / "test.ssd"
        with DFS.create_file(filepath, disk_format, title="Persist") as dfs:
            pass

        # Reopen read-only and verify title persisted
        with DFS.from_file(filepath, disk_format) as dfs:
            assert dfs.title.strip("\x00 ") == "Persist"
            assert len(dfs.files) == 0

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_create_file_with_data(self, disk_format, expected_total_sectors, catalogue_sectors, tmp_path):
        filepath = tmp_path / "test.ssd"
        with DFS.create_file(filepath, disk_format) as dfs:
            dfs.save("$.HELLO", b"Hello!")

        # Reopen and verify file data
        with DFS.from_file(filepath, disk_format) as dfs:
            assert dfs.load("$.HELLO") == b"Hello!"

    @pytest.mark.parametrize("disk_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_created_file_size(self, disk_format, expected_total_sectors, catalogue_sectors, tmp_path):
        filepath = tmp_path / "test.ssd"
        with DFS.create_file(filepath, disk_format):
            pass  # Just create
        # File should cover all surfaces
        expected_size = 0
        for spec in disk_format.surface_specs:
            end = (
                spec.track_zero_offset_bytes
                + (spec.num_tracks - 1) * spec.track_stride_bytes
                + spec.sectors_per_track * spec.bytes_per_sector
            )
            expected_size = max(expected_size, end)
        assert filepath.stat().st_size == expected_size


class TestDFSCreateEdgeCases:

    def test_create_double_sided_each_side_independent(self):
        """Each side of a DSD is independent — creating gives side 0."""
        dfs = DFS.create(ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED)
        dfs.save("$.SIDE0", b"side zero data")
        assert dfs.load("$.SIDE0") == b"side zero data"

    def test_create_with_side_parameter(self):
        """Creating with side=1 should give an empty side 1."""
        dfs = DFS.create(ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, side=1)
        assert len(dfs.files) == 0
        dfs.save("$.SIDE1", b"side one data")
        assert dfs.load("$.SIDE1") == b"side one data"

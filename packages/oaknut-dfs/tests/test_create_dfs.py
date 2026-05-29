"""Tests for DFS disc image creation.

Parameterised round-trip tests: create an empty disc image, verify the
catalogue is empty, the total sectors and free space match expectations,
and that files can be written and read back.
"""

import pytest
from oaknut.dfs.dfs import DFS
from oaknut.dfs.formats import (
    ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL,
    ACORN_DFS_40T_SINGLE_SIDED,
    ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL,
    ACORN_DFS_80T_SINGLE_SIDED,
    WATFORD_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
    WATFORD_DFS_40T_DOUBLE_SIDED_SEQUENTIAL,
    WATFORD_DFS_40T_SINGLE_SIDED,
    WATFORD_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
    WATFORD_DFS_80T_DOUBLE_SIDED_SEQUENTIAL,
    WATFORD_DFS_80T_SINGLE_SIDED,
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

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_empty_catalogue(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format)
        assert len(dfs.files) == 0

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_total_sectors(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format)
        disc_info = dfs._catalogued_surface.disc_info
        assert disc_info.total_sectors == expected_total_sectors

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_free_sectors(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format)
        assert dfs.free_sectors == expected_total_sectors - catalogue_sectors

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_default_title_is_empty(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format)
        assert dfs.title.strip("\x00 ") == ""

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_custom_title(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format, title="TestDisc")
        assert dfs.title.strip("\x00 ") == "TestDisc"

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_default_boot_option(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format)
        assert dfs.boot_option == 0

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_custom_boot_option(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format, boot_option=3)
        assert dfs.boot_option == 3

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_root_is_empty(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format)
        assert list(dfs.root) == []

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_validate_clean(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format)
        assert dfs.validate() == []


class TestDFSCreateRoundTrip:
    """Test writing files to created images and reading them back."""

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_save_and_load(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format)
        (dfs.root / "$" / "HELLO").write_bytes(b"Hello, World!", load_address=0x1900)
        assert len(dfs.files) == 1
        assert (dfs.root / "$" / "HELLO").read_bytes() == b"Hello, World!"

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_catalogue_high_bits_round_trip(
        self, disc_format, expected_total_sectors, catalogue_sectors
    ):
        """Verify that the high bits (16-17) of load, exec, and length
        are packed and unpacked correctly in the catalogue extra byte.

        Regression test: the write path previously used wrong bit shifts
        (>> 14, >> 12, >> 10 instead of >> 16), causing values with
        non-zero bits 12-15 but zero bits 16-17 to be stored incorrectly.
        """
        dfs = DFS.create(disc_format)
        # 15053 bytes — bits 12-13 of length are non-zero, bits 16-17 are zero
        data = b"x" * 15053
        (dfs.root / "$" / "PROG").write_bytes(data, load_address=0x0800, exec_address=0x8023)
        stat = (dfs.root / "$" / "PROG").stat()
        assert stat.length == 15053
        assert stat.load_address == 0x0800
        assert stat.exec_address == 0x8023
        assert (dfs.root / "$" / "PROG").read_bytes() == data

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_save_and_load_via_path(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format)
        (dfs.root / "$" / "DATA").write_bytes(b"test data", load_address=0x2000)
        data = (dfs.root / "$" / "DATA").read_bytes()
        assert data == b"test data"

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_free_sectors_decrease_after_save(
        self, disc_format, expected_total_sectors, catalogue_sectors
    ):
        dfs = DFS.create(disc_format)
        initial_free = dfs.free_sectors
        (dfs.root / "$" / "FILE").write_bytes(b"x" * 512)  # 2 sectors
        assert dfs.free_sectors == initial_free - 2

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_save_delete_roundtrip(self, disc_format, expected_total_sectors, catalogue_sectors):
        dfs = DFS.create(disc_format)
        initial_free = dfs.free_sectors
        (dfs.root / "$" / "TEMP").write_bytes(b"temporary")
        (dfs.root / "$" / "TEMP").unlink()
        assert len(dfs.files) == 0
        # Free sectors restored after compaction
        dfs.compact()
        assert dfs.free_sectors == initial_free


class TestDFSCreateFile:
    """Test DFS.create_file() for file-backed disc images."""

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_create_file_empty_and_reopen(
        self, disc_format, expected_total_sectors, catalogue_sectors, tmp_path
    ):
        filepath = tmp_path / "test.ssd"
        with DFS.create_file(filepath, disc_format, title="Persist") as dfs:
            pass

        # Reopen read-only and verify title persisted
        with DFS.from_file(filepath, disc_format) as dfs:
            assert dfs.title.strip("\x00 ") == "Persist"
            assert len(dfs.files) == 0

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_create_file_with_data(
        self, disc_format, expected_total_sectors, catalogue_sectors, tmp_path
    ):
        filepath = tmp_path / "test.ssd"
        with DFS.create_file(filepath, disc_format) as dfs:
            (dfs.root / "$" / "HELLO").write_bytes(b"Hello!")

        # Reopen and verify file data
        with DFS.from_file(filepath, disc_format) as dfs:
            assert (dfs.root / "$" / "HELLO").read_bytes() == b"Hello!"

    @pytest.mark.parametrize("disc_format,expected_total_sectors,catalogue_sectors", ALL_FORMATS)
    def test_created_file_size(
        self, disc_format, expected_total_sectors, catalogue_sectors, tmp_path
    ):
        filepath = tmp_path / "test.ssd"
        with DFS.create_file(filepath, disc_format):
            pass  # Just create
        # File should cover all surfaces
        expected_size = 0
        for spec in disc_format.surface_specs:
            end = (
                spec.track_zero_offset_bytes
                + (spec.num_tracks - 1) * spec.track_stride_bytes
                + spec.sectors_per_track * spec.bytes_per_sector
            )
            expected_size = max(expected_size, end)
        assert filepath.stat().st_size == expected_size


class TestDFSCreateFormatsAllSurfaces:
    """Creating a multi-surface disc formats *every* surface, not just side 0.

    A DSD carries two independent DFS volumes; both must be a valid empty
    catalogue after creation, so the second side is immediately usable
    (e.g. assembling a DSD from two SSDs). Regression: previously only
    side 0 was initialised, leaving side 1 a zero-sector non-disc.
    """

    DOUBLE_SIDED = [
        pytest.param(ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, 800, id="acorn-80t-dsi"),
        pytest.param(ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL, 800, id="acorn-80t-dss"),
        pytest.param(ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, 400, id="acorn-40t-dsi"),
        pytest.param(WATFORD_DFS_80T_DOUBLE_SIDED_INTERLEAVED, 800, id="watford-80t-dsi"),
    ]

    @pytest.mark.parametrize("disc_format,per_side_sectors", DOUBLE_SIDED)
    def test_create_file_formats_second_side(self, disc_format, per_side_sectors, tmp_path):
        filepath = tmp_path / "test.dsd"
        with DFS.create_file(filepath, disc_format, title="FRONT"):
            pass
        # Side 1 must be a valid, empty catalogue — not a zero-sector disc.
        with DFS.from_file(filepath, disc_format, side=1) as side1:
            assert side1._catalogued_surface.disc_info.total_sectors == per_side_sectors
            assert len(side1.files) == 0

    @pytest.mark.parametrize("disc_format,per_side_sectors", DOUBLE_SIDED)
    def test_create_file_sides_are_independent(self, disc_format, per_side_sectors, tmp_path):
        filepath = tmp_path / "test.dsd"
        with DFS.create_file(filepath, disc_format, title="FRONT") as side0:
            (side0.root / "$" / "ONLY0").write_bytes(b"only on side 0")
        # Writing side 0 must not have touched side 1's empty catalogue.
        with DFS.from_file(filepath, disc_format, side=1) as side1:
            assert len(side1.files) == 0
            (side1.root / "$" / "ONLY2").write_bytes(b"only on side 2")
        # And each side now holds exactly its own file.
        with DFS.from_file(filepath, disc_format, side=0) as side0:
            assert [str(p) for p in (side0.root / "$").iterdir()] == ["$.ONLY0"]
        with DFS.from_file(filepath, disc_format, side=1) as side1:
            assert [str(p) for p in (side1.root / "$").iterdir()] == ["$.ONLY2"]

    def test_create_file_title_applies_to_side_zero_only(self, tmp_path):
        """The create title names side 0; other surfaces start untitled."""
        filepath = tmp_path / "test.dsd"
        with DFS.create_file(
            filepath, ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, title="FRONT"
        ):
            pass
        with DFS.from_file(filepath, ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, side=0) as s0:
            assert s0.title == "FRONT"
        with DFS.from_file(filepath, ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, side=1) as s1:
            assert s1.title == ""


class TestDFSCreateEdgeCases:
    def test_create_double_sided_each_side_independent(self):
        """Each side of a DSD is independent — creating gives side 0."""
        dfs = DFS.create(ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED)
        (dfs.root / "$" / "SIDE0").write_bytes(b"side zero data")
        assert (dfs.root / "$" / "SIDE0").read_bytes() == b"side zero data"

    def test_create_with_side_parameter(self):
        """Creating with side=1 should give an empty side 1."""
        dfs = DFS.create(ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, side=1)
        assert len(dfs.files) == 0
        (dfs.root / "$" / "SIDE1").write_bytes(b"side one data")
        assert (dfs.root / "$" / "SIDE1").read_bytes() == b"side one data"

"""Tests for creating ADFS hard disc images.

Tests cover:
- geometry_for_capacity: sensible geometry from a capacity request
- create_file with .dat extension: writes .dat + .dsc pair
- create with explicit geometry and custom SPT
- round-trip: create, reopen, verify
"""


import pytest

from oaknut_dfs.adfs import (
    ADFS,
    _parse_dsc,
    geometry_for_capacity,
)


# --- geometry_for_capacity tests ---


class TestGeometryForCapacity:

    def test_10mb(self):
        geom = geometry_for_capacity(10 * 1024 * 1024)
        actual_bytes = geom.cylinders * geom.heads * geom.sectors_per_track * 256
        assert actual_bytes >= 10 * 1024 * 1024

    def test_20mb(self):
        geom = geometry_for_capacity(20 * 1024 * 1024)
        actual_bytes = geom.cylinders * geom.heads * geom.sectors_per_track * 256
        assert actual_bytes >= 20 * 1024 * 1024

    def test_default_spt_is_33(self):
        geom = geometry_for_capacity(10 * 1024 * 1024)
        assert geom.sectors_per_track == 33

    def test_default_heads_is_4(self):
        geom = geometry_for_capacity(10 * 1024 * 1024)
        assert geom.heads == 4

    def test_custom_spt(self):
        geom = geometry_for_capacity(10 * 1024 * 1024, sectors_per_track=17)
        assert geom.sectors_per_track == 17
        actual_bytes = geom.cylinders * geom.heads * geom.sectors_per_track * 256
        assert actual_bytes >= 10 * 1024 * 1024

    def test_custom_heads(self):
        geom = geometry_for_capacity(10 * 1024 * 1024, heads=2)
        assert geom.heads == 2
        actual_bytes = geom.cylinders * geom.heads * geom.sectors_per_track * 256
        assert actual_bytes >= 10 * 1024 * 1024

    def test_small_capacity(self):
        """Even a small capacity produces a valid geometry."""
        geom = geometry_for_capacity(100 * 1024)  # 100KB
        actual_bytes = geom.cylinders * geom.heads * geom.sectors_per_track * 256
        assert actual_bytes >= 100 * 1024
        assert geom.cylinders >= 1

    def test_not_much_larger_than_requested(self):
        """Result should be close to the requested capacity, not wildly larger."""
        requested = 10 * 1024 * 1024
        geom = geometry_for_capacity(requested)
        actual_bytes = geom.cylinders * geom.heads * geom.sectors_per_track * 256
        # Should be within one cylinder of the target
        cylinder_bytes = geom.heads * geom.sectors_per_track * 256
        assert actual_bytes < requested + cylinder_bytes

    def test_zero_capacity_raises(self):
        with pytest.raises(ValueError):
            geometry_for_capacity(0)

    def test_negative_capacity_raises(self):
        with pytest.raises(ValueError):
            geometry_for_capacity(-1)


# --- create_file with .dat extension ---


class TestCreateHardDiscFile:

    def test_creates_dat_and_dsc(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(dat_filepath, capacity_bytes=1024 * 1024):
            pass
        assert dat_filepath.exists()
        assert (tmp_path / "test.dsc").exists()

    def test_dsc_is_22_bytes(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(dat_filepath, capacity_bytes=1024 * 1024):
            pass
        assert (tmp_path / "test.dsc").stat().st_size == 22

    def test_dsc_geometry_matches(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(
            dat_filepath, cylinders=100, heads=4, sectors_per_track=33
        ):
            pass
        geom = _parse_dsc(tmp_path / "test.dsc")
        assert geom.cylinders == 100
        assert geom.heads == 4

    def test_empty_root(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(dat_filepath, capacity_bytes=1024 * 1024) as adfs:
            assert list(adfs.root) == []

    def test_custom_title(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(
            dat_filepath, capacity_bytes=1024 * 1024, title="MyHDD"
        ) as adfs:
            assert adfs.title == "MyHDD"

    def test_custom_boot_option(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(
            dat_filepath, capacity_bytes=1024 * 1024, boot_option=2
        ) as adfs:
            assert adfs.boot_option == 2

    def test_validate_clean(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(dat_filepath, capacity_bytes=1024 * 1024) as adfs:
            assert adfs.validate() == []

    def test_free_space(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(dat_filepath, cylinders=10, heads=4) as adfs:
            total_sectors = 10 * 4 * 33
            expected_free = (total_sectors - 7) * 256  # FSM(2) + root(5) = 7
            assert adfs.free_space == expected_free

    def test_explicit_geometry(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(
            dat_filepath, cylinders=50, heads=2, sectors_per_track=33
        ):
            pass
        expected_size = 50 * 2 * 33 * 256
        assert dat_filepath.stat().st_size == expected_size

    def test_custom_spt(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(
            dat_filepath, cylinders=50, heads=2, sectors_per_track=17
        ):
            pass
        expected_size = 50 * 2 * 17 * 256
        assert dat_filepath.stat().st_size == expected_size


class TestCreateHardDiscRoundTrip:

    def test_create_and_reopen(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(
            dat_filepath, capacity_bytes=1024 * 1024, title="RoundTrip"
        ):
            pass

        with ADFS.from_file(dat_filepath) as adfs:
            assert adfs.title == "RoundTrip"
            assert list(adfs.root) == []

    def test_reopen_via_dsc(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        dsc_filepath = tmp_path / "test.dsc"
        with ADFS.create_file(dat_filepath, capacity_bytes=1024 * 1024):
            pass

        with ADFS.from_file(dsc_filepath) as adfs:
            assert adfs.root.is_dir()

    def test_walk_after_reopen(self, tmp_path):
        dat_filepath = tmp_path / "test.dat"
        with ADFS.create_file(
            dat_filepath, capacity_bytes=2 * 1024 * 1024, title="WalkTest"
        ):
            pass

        with ADFS.from_file(dat_filepath) as adfs:
            results = list(adfs.root.walk())
            assert len(results) == 1
            dirpath, dirnames, filenames = results[0]
            assert str(dirpath) == "$"
            assert dirnames == []
            assert filenames == []


class TestCreateHardDiscErrors:

    def test_capacity_and_cylinders_mutually_exclusive(self, tmp_path):
        """Cannot specify both capacity_bytes and explicit cylinders."""
        dat_filepath = tmp_path / "test.dat"
        with pytest.raises((ValueError, TypeError)):
            with ADFS.create_file(
                dat_filepath, capacity_bytes=1024 * 1024, cylinders=100
            ):
                pass

    def test_dat_requires_capacity_or_geometry(self, tmp_path):
        """A .dat file needs either capacity_bytes or cylinders/heads."""
        dat_filepath = tmp_path / "test.dat"
        with pytest.raises((ValueError, TypeError)):
            with ADFS.create_file(dat_filepath):
                pass

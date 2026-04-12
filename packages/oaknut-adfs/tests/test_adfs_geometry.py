"""Tests for ADFSGeometry — authoritative disc geometry on ADFS objects."""

from pathlib import Path

import pytest
from oaknut.adfs import ADFS, ADFS_L, ADFS_M, ADFS_S, ADFSGeometry


class TestADFSGeometryDataclass:
    def test_sectors_per_cylinder(self):
        g = ADFSGeometry(cylinders=100, heads=4, sectors_per_track=33)
        assert g.sectors_per_cylinder == 132

    def test_total_sectors(self):
        g = ADFSGeometry(cylinders=100, heads=4, sectors_per_track=33)
        assert g.total_sectors == 13200


class TestGeometryFromFloppyCreate:
    def test_adfs_s_geometry(self):
        adfs = ADFS.create(ADFS_S)
        g = adfs.geometry
        assert g.cylinders == 40
        assert g.heads == 1
        assert g.sectors_per_track == 16
        assert g.total_sectors == 640

    def test_adfs_m_geometry(self):
        adfs = ADFS.create(ADFS_M)
        g = adfs.geometry
        assert g.cylinders == 80
        assert g.heads == 1
        assert g.sectors_per_track == 16
        assert g.total_sectors == 1280

    def test_adfs_l_geometry(self):
        adfs = ADFS.create(ADFS_L)
        g = adfs.geometry
        assert g.cylinders == 80
        assert g.heads == 2
        assert g.sectors_per_track == 16
        assert g.total_sectors == 2560


class TestGeometryFromFloppyBuffer:
    def test_adfs_s_buffer(self):
        adfs = ADFS.create(ADFS_S)
        g = adfs.geometry
        assert g.cylinders == 40
        assert g.sectors_per_track == 16


class TestGeometryFromHardDiscCreate:
    def test_hard_disc_explicit_geometry(self, tmp_path: Path):
        filepath = tmp_path / "scsi0.dat"
        with ADFS.create_file(
            filepath, cylinders=100, heads=4, sectors_per_track=33,
        ) as adfs:
            g = adfs.geometry
            assert g.cylinders == 100
            assert g.heads == 4
            assert g.sectors_per_track == 33
            assert g.sectors_per_cylinder == 132
            assert g.total_sectors == 13200

    def test_hard_disc_from_capacity(self, tmp_path: Path):
        filepath = tmp_path / "scsi0.dat"
        with ADFS.create_file(filepath, capacity_bytes=5 * 1024 * 1024) as adfs:
            g = adfs.geometry
            assert g.heads == 4
            assert g.sectors_per_track == 33
            assert g.cylinders > 0
            assert g.total_sectors == g.cylinders * g.sectors_per_cylinder


class TestGeometryFromHardDiscFile:
    def test_round_trip_through_file(self, tmp_path: Path):
        """Create a hard disc, close it, reopen — geometry should be preserved."""
        filepath = tmp_path / "scsi0.dat"
        with ADFS.create_file(filepath, cylinders=50, heads=4) as adfs:
            original = adfs.geometry

        with ADFS.from_file(filepath) as adfs:
            reopened = adfs.geometry
            assert reopened.cylinders == original.cylinders
            assert reopened.heads == original.heads
            assert reopened.sectors_per_track == original.sectors_per_track

"""Tests for ADFSGeometry — authoritative disc geometry on ADFS objects."""

from pathlib import Path

import pytest
from oaknut.adfs import (
    ADFS,
    ADFS_D,
    ADFS_E,
    ADFS_F,
    ADFS_G,
    ADFS_L,
    ADFS_M,
    ADFS_S,
    ADFSGeometry,
)


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

    # New-directory and New-map floppies. Geometry is expressed in ADFS's
    # 256-byte logical sectors (as S/M/L are), so sectors-per-track counts the
    # 1024-byte physical sectors times four, and total_sectors == bytes / 256.
    @pytest.mark.parametrize(
        "fmt,heads,spt,total",
        [
            (ADFS_D, 2, 20, 3200),  # 800 KB
            (ADFS_E, 2, 20, 3200),  # 800 KB
            (ADFS_F, 2, 40, 6400),  # 1.6 MB, four zones
            (ADFS_G, 2, 80, 12800),  # 3.2 MB, eight zones
        ],
    )
    def test_new_floppy_geometry(self, fmt, heads, spt, total):
        g = ADFS.create(fmt).geometry
        assert g.cylinders == 80
        assert g.heads == heads
        assert g.sectors_per_track == spt
        # The geometry must account for the whole disc.
        assert g.total_sectors == total == fmt.total_bytes // 256


class TestGeometryFromFloppyBuffer:
    def test_adfs_s_buffer(self):
        adfs = ADFS.create(ADFS_S)
        g = adfs.geometry
        assert g.cylinders == 40
        assert g.sectors_per_track == 16

    @pytest.mark.parametrize("fmt", [ADFS_D, ADFS_E, ADFS_F, ADFS_G])
    def test_new_floppy_reopen_geometry_matches_create(self, fmt, tmp_path):
        # Regression: reopening an F or G image reported a degenerate
        # 1 cylinder x 1 head x N sectors/track shape, disagreeing with what
        # create() produced. The reopened geometry must match create() and
        # describe a real floppy (more than one cylinder and head).
        image = tmp_path / "disc.adf"
        with ADFS.create_file(str(image), fmt, title="T"):
            pass
        created = ADFS.create(fmt).geometry
        with ADFS.from_file(image, read_only=True) as adfs:
            reopened = adfs.geometry
        assert (reopened.cylinders, reopened.heads, reopened.sectors_per_track) == (
            created.cylinders,
            created.heads,
            created.sectors_per_track,
        )
        assert reopened.cylinders > 1 and reopened.heads > 1
        assert reopened.total_sectors == fmt.total_bytes // 256


class TestGeometryFromHardDiscCreate:
    def test_hard_disc_explicit_geometry(self, tmp_path: Path):
        filepath = tmp_path / "scsi0.dat"
        with ADFS.create_file(
            filepath,
            cylinders=100,
            heads=4,
            sectors_per_track=33,
        ) as adfs:
            g = adfs.geometry
            assert g.cylinders == 100
            assert g.heads == 4
            assert g.sectors_per_track == 33
            assert g.sectors_per_cylinder == 132
            assert g.total_sectors == 13200

    def test_hard_disc_from_capacity(self, tmp_path: Path):
        filepath = tmp_path / "scsi0.dat"
        with ADFS.create_file(filepath, capacity=5 * 1024 * 1024) as adfs:
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

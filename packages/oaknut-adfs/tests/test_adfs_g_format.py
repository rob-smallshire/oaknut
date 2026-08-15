"""ADFS G format: 3.2MB octal-density eight-zone New Map floppy.

G is the natural doubling of F — twice the sectors per track (20), octal
density, and eight zones instead of four — while keeping F's 1024-byte
sectors, 64-byte map granularity and 15-bit fragment ids. It is a rare
format; no reference formatter (DiscImageManager included) writes it, so
the disc record is derived from FileCore's own map invariants and verified
by round-trip through our reader.
"""

from __future__ import annotations

import pytest
from oaknut.adfs.adfs import ADFS, ADFS_G, ADFS_G_PLUS
from oaknut.adfs.directory import BigDirectoryFormat, NewDirectoryFormat


def test_g_geometry():
    assert ADFS_G.total_bytes == 3276800  # 3.2MB
    assert ADFS_G.new_map and not ADFS_G.big_directories
    assert ADFS_G_PLUS.total_bytes == 3276800
    assert ADFS_G_PLUS.big_directories


@pytest.mark.parametrize(
    "fmt,big,root",
    [(ADFS_G, False, 0x211), (ADFS_G_PLUS, True, 0x67001)],
)
def test_g_disc_record(fmt, big, root):
    adfs = ADFS.create(fmt, title="GDisc")
    try:
        dr = adfs._map.disc_record
        assert dr.disc_size == 3276800
        assert dr.nzones == 8
        assert dr.density == 8  # octal
        assert dr.sectors_per_track == 20
        assert dr.sector_size == 1024
        assert dr.root == root
        assert dr.uses_big_directories is big
        # A G floppy is NOT a hard disc, so it carries no HDD hardware info.
        raw = bytes(adfs._disc.sector_range(0, dr.disc_size // 256))
        assert raw[0xDBB] == 0x00  # no initialised flag (that is a hard-disc field)
        assert adfs.validate() == []
    finally:
        adfs.close()


@pytest.mark.parametrize("fmt,big", [(ADFS_G, False), (ADFS_G_PLUS, True)])
def test_g_write_round_trip(fmt, big):
    adfs = ADFS.create(fmt, title="GData")
    try:
        expected = BigDirectoryFormat if big else NewDirectoryFormat
        assert isinstance(adfs._dir_format, expected)

        def name(i):
            return f"LongFileName_{i:03d}" if big else f"File{i:03d}"

        payloads = {name(i): bytes([i & 0xFF]) * (600 + i * 40) for i in range(40)}
        for n, data in payloads.items():
            (adfs.root / n).write_bytes(data)
        (adfs.root / ("SubDirectoryName" if big else "Sub")).mkdir()
        assert adfs.validate() == []
        for n, data in payloads.items():
            assert (adfs.root / n).read_bytes() == data
    finally:
        adfs.close()


def test_g_spans_multiple_zones():
    # Enough data to push allocation past the first zone, exercising the
    # multi-zone fragment search on an eight-zone disc.
    adfs = ADFS.create(ADFS_G, title="GBig")
    try:
        payload = bytes(range(256)) * 1024  # 256KB per file
        for i in range(6):
            (adfs.root / f"Big{i:02d}").write_bytes(payload)
        assert adfs.validate() == []
        for i in range(6):
            assert (adfs.root / f"Big{i:02d}").read_bytes() == payload
    finally:
        adfs.close()


def test_g_persists(tmp_path):
    image = tmp_path / "disc.adf"
    with ADFS.create_file(image, ADFS_G, title="GPersist") as adfs:
        for i in range(20):
            (adfs.root / f"File{i:03d}").write_bytes(bytes([i]) * (300 + i))
    with ADFS.from_file(image) as adfs:
        assert adfs.is_new_map
        assert adfs._map.disc_record.nzones == 8
        assert adfs.validate() == []
        for i in range(20):
            assert (adfs.root / f"File{i:03d}").read_bytes() == bytes([i]) * (300 + i)

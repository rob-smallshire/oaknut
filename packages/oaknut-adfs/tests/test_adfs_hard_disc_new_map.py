"""New Map hard disc reading: many zones and the .hdf 0x200 header offset.

New-map hard discs are just large multi-zone New Map discs, so the existing
multi-zone reader handles arbitrary zone counts, 512-byte sectors and other
idlen/bpmb values. Emulator hard disc images (``.hdf``/``.hd4``) prepend a
0x200-byte header, shifting the whole disc by 0x200 modulo the disc size;
detection probes both offsets.

A real 26-zone RISC OS HDD (Arculator's ``hd4.hdf``, ~50 MB) is too large to
commit, so it is used transiently when present in the scratchpad; the 0x200
mechanism itself is covered durably by rotating a created F image.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs.adfs import ADFS, ADFS_F
from oaknut.adfs.directory import BigDirectoryFormat, NewDirectoryFormat
from oaknut.adfs.new_map import hard_drive_params

_HD4 = (
    Path("/private/tmp/claude-501/-Users-rjs-Code-oaknut")
    .glob("*/scratchpad/hd4.hdf")
)


def _rotate_as_hdf(disc: bytes, header: int = 0x200) -> bytes:
    """Present *disc* as an emulator image: disc byte D lands at (D+header) mod size.

    The last *header* bytes move to the front (the "header" region), so the file
    size still equals the disc size and the tail wraps into the header — exactly
    what a ``.hdf`` does.
    """
    return disc[len(disc) - header :] + disc[: len(disc) - header]


def test_hdf_offset_detected_and_read_by_rotation():
    # Build a populated F disc, then rotate it into .hdf form and re-read.
    adfs = ADFS.create(ADFS_F, title="RotF")
    try:
        payload = {f"File{i}": bytes([i]) * (1000 + i) for i in range(8)}
        for name, data in payload.items():
            (adfs.root / name).write_bytes(data)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir" / "Nested").write_bytes(b"nested")
        disc = bytes(adfs._disc.sector_range(0, ADFS_F.total_sectors))
    finally:
        adfs.close()

    hdf = _rotate_as_hdf(disc)
    reopened = ADFS.from_buffer(memoryview(bytearray(hdf)))
    try:
        assert reopened.is_new_map
        assert reopened._map._base_offset == 0x200
        assert reopened.validate() == []
        assert {p.name for p in reopened.root.iterdir()} == set(payload) | {"Dir"}
        for name, data in payload.items():
            assert (reopened.root / name).read_bytes() == data
        assert (reopened.root / "Dir" / "Nested").read_bytes() == b"nested"
    finally:
        reopened.close()


@pytest.mark.skipif(not next(_HD4, None), reason="Arculator hd4.hdf not in scratchpad")
def test_read_real_arculator_hdd():
    hd4 = next(
        Path("/private/tmp/claude-501/-Users-rjs-Code-oaknut").glob("*/scratchpad/hd4.hdf")
    )
    with ADFS.from_file(hd4) as adfs:
        assert adfs.is_new_map
        assert adfs._map.disc_record.nzones == 26
        assert adfs._map.disc_record.sector_size == 512
        assert adfs._map._base_offset == 0x200
        assert adfs.validate() == []

        def count(path):
            n = 0
            for child in path.iterdir():
                n += 1
                if child.is_dir():
                    n += count(child)
                else:
                    assert len(child.read_bytes()) == child.stat().length
            return n

        assert count(adfs.root) > 100  # a real, populated disc


def test_hard_drive_params_are_valid():
    for size in (4 * 1024 * 1024, 20 * 1024 * 1024, 100 * 1024 * 1024):
        params = hard_drive_params(size)
        assert params is not None
        # idlen must hold every id across the zones, and be at least log2secsize+3.
        ids_per_zone = ((1 << params["log2_sector_size"]) * 8 - params["zone_spare"]) // (
            params["idlen"] + 1
        )
        assert ids_per_zone * params["nzones"] <= (1 << params["idlen"])
        assert params["idlen"] >= params["log2_sector_size"] + 3


@pytest.mark.parametrize("big", [False, True])
def test_create_new_map_hard_disc_round_trip(big):
    adfs = ADFS.create_new_map_hard_disc("8MB", title="MyHDD", big_directories=big)
    try:
        expected = BigDirectoryFormat if big else NewDirectoryFormat
        assert isinstance(adfs._dir_format, expected)
        assert adfs._map.disc_record.nzones > 1  # multi-zone
        assert list(adfs.root.iterdir()) == []
        assert adfs.validate() == []

        def name(i):
            return f"LongFileName_{i:03d}" if big else f"File{i:03d}"

        payloads = {name(i): bytes([i & 0xFF]) * (500 + i * 30) for i in range(30)}
        for n, data in payloads.items():
            (adfs.root / n).write_bytes(data)
        (adfs.root / ("SubDirectoryName" if big else "Sub")).mkdir()
        assert adfs.validate() == []
        for n, data in payloads.items():
            assert (adfs.root / n).read_bytes() == data
    finally:
        adfs.close()


def test_create_new_map_hard_disc_persists(tmp_path):
    image = tmp_path / "hd.dat"
    adfs = ADFS.create_new_map_hard_disc("6MB", title="Persist")
    try:
        for i in range(20):
            (adfs.root / f"File{i:03d}").write_bytes(bytes([i]) * (300 + i))
        raw = bytes(adfs._disc.sector_range(0, adfs._map.disc_record.disc_size // 256))
    finally:
        adfs.close()
    image.write_bytes(raw)
    with ADFS.from_file(image) as adfs:  # .dat, no .dsc — read by content
        assert adfs.is_new_map
        assert adfs.validate() == []
        for i in range(20):
            assert (adfs.root / f"File{i:03d}").read_bytes() == bytes([i]) * (300 + i)


def test_created_hdd_is_emulator_mountable_structure():
    """A created IDE HDD has the lowsector layout, hardware info and init flag
    that RISC OS and emulators require to mount it (matching a real .hdf)."""
    from oaknut.adfs.new_map import _boot_block_checksum

    adfs = ADFS.create_new_map_hard_disc("8MB", title="Mountable")
    try:
        dr = adfs._map.disc_record
        assert dr.low_sector == 1  # IDE
        assert adfs._map._base_offset == dr.low_sector * dr.sector_size  # 0x200
        raw = bytes(adfs._disc.sector_range(0, dr.disc_size // 256))
    finally:
        adfs.close()

    boot = dr.low_sector * dr.sector_size + 0xC00  # boot block, shifted by lowsector
    # The initialised flag — without it RISC OS treats the disc as unformatted.
    assert raw[boot + 0x1BB] == 0x01
    assert raw[boot + 0x1AC : boot + 0x1B0] == b"\xff\xff\xff\xff"
    # The boot block checksum is valid.
    assert raw[boot + 0x1FF] == _boot_block_checksum(bytearray(raw[boot : boot + 0x200]), 0, 0x200)
    # The header region (the wrapped disc tail) is unused, as on real .hdf images.
    assert all(b == 0 for b in raw[: dr.low_sector * dr.sector_size])

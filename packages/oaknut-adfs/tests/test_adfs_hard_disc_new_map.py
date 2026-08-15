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

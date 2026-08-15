"""Multi-fragment allocation on New Map discs.

FileCore splits an object across several fragments (sharing one fragment
id) when no single free area is large enough. These tests fragment a disc
by deleting alternate files, then write objects that must span the holes —
and, on the multi-zone F format, span zones in the correct order.
"""

from __future__ import annotations

from oaknut.adfs.adfs import ADFS, ADFS_E, ADFS_F


def _frag_id(path):
    _, entry = path._resolve()
    return entry.indirect_disc_address >> 8


def _fragment_disc(adfs, n=20, size=4000):
    for i in range(n):
        (adfs.root / f"F{i:02d}").write_bytes(bytes([i]) * size)
    for i in range(0, n, 2):
        (adfs.root / f"F{i:02d}").unlink()
    assert adfs.validate() == []


def test_e_multi_fragment_file():
    adfs = ADFS.create(ADFS_E, title="FragE")
    try:
        _fragment_disc(adfs)
        payload = bytes((i * 7) & 0xFF for i in range(30000))
        (adfs.root / "Big").write_bytes(payload)
        assert adfs.validate() == []
        big = adfs.root / "Big"
        assert len(adfs._map._fragments[_frag_id(big)]) > 1  # genuinely fragmented
        assert big.read_bytes() == payload
    finally:
        adfs.close()


def test_e_disc_full_uses_scattered_free():
    """A file that fits only across scattered holes now succeeds (was refused)."""
    adfs = ADFS.create(ADFS_E, title="ScatterE")
    try:
        _fragment_disc(adfs, n=30, size=4000)
        total_free = adfs.free_space
        # One object as large as most of the remaining free space.
        payload = bytes(total_free // 2)
        (adfs.root / "Fill").write_bytes(payload)
        assert adfs.validate() == []
        assert (adfs.root / "Fill").read_bytes() == payload
    finally:
        adfs.close()


def test_f_multi_fragment_within_zone():
    adfs = ADFS.create(ADFS_F, title="FragF")
    try:
        _fragment_disc(adfs)
        payload = bytes((i * 5) & 0xFF for i in range(30000))
        (adfs.root / "Big").write_bytes(payload)
        assert adfs.validate() == []
        big = adfs.root / "Big"
        assert len(adfs._map._fragments[_frag_id(big)]) > 1
        assert big.read_bytes() == payload
    finally:
        adfs.close()


def test_f_object_spans_zones_in_order():
    """A file larger than one zone spans zones and reads back in order."""
    adfs = ADFS.create(ADFS_F, title="SpanF")
    try:
        # One zone holds ~ (8192-1600)*64 ≈ 420 KB; make the file clearly larger.
        payload = bytes((i * 11) & 0xFF for i in range(600_000))
        (adfs.root / "Huge").write_bytes(payload)
        assert adfs.validate() == []
        huge = adfs.root / "Huge"
        fragments = adfs._map._fragments[_frag_id(huge)]
        zones = {zone for _, _, zone in fragments}
        assert len(zones) >= 2, f"expected multi-zone object, got zones {zones}"
        assert huge.read_bytes() == payload  # correct cross-zone ordering
    finally:
        adfs.close()

"""Tests for oaknut.afs.bitmap.

Two layers under test: :class:`CylinderBitmap` (pure, self-contained)
and :class:`BitmapShadow` (lazy cache with reader/writer callbacks).

Ground truth for byte ordering comes from Beebmaster's PDF pp.7-8:

    "Under our Test Disc example, contents of sector &50 (being
    sector 0 of cylinder 5) would contain the bit map for that
    cylinder. As there are 16 sectors per cylinder on the disc, only
    16 bits are required, taking up two bytes. We know that sectors
    0 and 1 of cylinder 5 are occupied ... the bit map should
    therefore be:
        byte 0 = 128+64+32+16+8+4 = &FC
        byte 1 = 128+64+32+16+8+4+2+1 = &FF"
"""

from __future__ import annotations

import pytest
from oaknut.afs.bitmap import (
    BITMAP_SECTOR_SIZE,
    MAX_SECTORS_PER_CYLINDER,
    BitmapShadow,
    CylinderBitmap,
)

# ---------------------------------------------------------------------------
# CylinderBitmap: byte ordering (Beebmaster PDF p.8 example)
# ---------------------------------------------------------------------------


class TestBeebmasterBitmapExample:
    """Reproduce the PDF's worked example for cylinder 5 of the test disc."""

    SECTORS_PER_CYLINDER = 16

    def _bitmap_with_sectors_0_and_1_allocated(self) -> CylinderBitmap:
        bitmap = CylinderBitmap.fresh(self.SECTORS_PER_CYLINDER)
        bitmap.set_allocated(1)  # sector 1 is the info sector sec1
        # sector 0 is already allocated by fresh()
        return bitmap

    def test_byte_0_is_FC(self) -> None:
        bitmap = self._bitmap_with_sectors_0_and_1_allocated()
        assert bitmap.to_bytes()[0] == 0xFC

    def test_byte_1_is_FF(self) -> None:
        bitmap = self._bitmap_with_sectors_0_and_1_allocated()
        assert bitmap.to_bytes()[1] == 0xFF

    def test_free_count_is_14(self) -> None:
        bitmap = self._bitmap_with_sectors_0_and_1_allocated()
        assert bitmap.free_count() == 14

    def test_allocated_count_is_2(self) -> None:
        bitmap = self._bitmap_with_sectors_0_and_1_allocated()
        assert bitmap.allocated_count() == 2


# ---------------------------------------------------------------------------
# CylinderBitmap: fresh cylinder
# ---------------------------------------------------------------------------


class TestFresh:
    def test_sector_0_is_allocated(self) -> None:
        assert CylinderBitmap.fresh(16).is_allocated(0)

    def test_other_sectors_are_free(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        for s in range(1, 16):
            assert bitmap.is_free(s), f"sector {s} should be free"

    def test_free_count_matches(self) -> None:
        assert CylinderBitmap.fresh(16).free_count() == 15

    def test_fresh_byte_0_is_FE(self) -> None:
        """Bits 1-7 set (free), bit 0 clear (allocated) → 0xFE."""
        assert CylinderBitmap.fresh(16).to_bytes()[0] == 0xFE


# ---------------------------------------------------------------------------
# CylinderBitmap: set_allocated / set_free symmetry
# ---------------------------------------------------------------------------


class TestAllocateFree:
    def test_set_allocated_then_set_free_restores(self) -> None:
        bitmap = CylinderBitmap.fresh(32)
        before = bitmap.to_bytes()
        bitmap.set_allocated(5)
        bitmap.set_allocated(10)
        bitmap.set_allocated(31)
        bitmap.set_free(5)
        bitmap.set_free(10)
        bitmap.set_free(31)
        assert bitmap.to_bytes() == before

    def test_set_allocated_is_idempotent(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        bitmap.set_allocated(5)
        before = bitmap.to_bytes()
        bitmap.set_allocated(5)
        assert bitmap.to_bytes() == before

    def test_set_free_is_idempotent(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        before = bitmap.to_bytes()
        bitmap.set_free(10)  # already free
        assert bitmap.to_bytes() == before


# ---------------------------------------------------------------------------
# CylinderBitmap: find_first_free
# ---------------------------------------------------------------------------


class TestFindFirstFree:
    def test_fresh_returns_1(self) -> None:
        assert CylinderBitmap.fresh(16).find_first_free() == 1

    def test_after_allocating_1(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        bitmap.set_allocated(1)
        assert bitmap.find_first_free() == 2

    def test_fully_allocated_returns_none(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        for s in range(1, 16):
            bitmap.set_allocated(s)
        assert bitmap.find_first_free() is None

    def test_with_start(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        assert bitmap.find_first_free(start=5) == 5
        bitmap.set_allocated(5)
        assert bitmap.find_first_free(start=5) == 6

    def test_start_beyond_cylinder_returns_none(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        assert bitmap.find_first_free(start=100) is None


class TestIterFree:
    def test_fresh(self) -> None:
        assert list(CylinderBitmap.fresh(16).iter_free()) == list(range(1, 16))

    def test_after_some_allocations(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        bitmap.set_allocated(3)
        bitmap.set_allocated(7)
        assert list(bitmap.iter_free()) == [1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15]


# ---------------------------------------------------------------------------
# CylinderBitmap: range mutations
# ---------------------------------------------------------------------------


class TestRangeMutations:
    def test_mark_range_allocated(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        bitmap.mark_range_allocated(1, 5)
        for s in range(1, 6):
            assert bitmap.is_allocated(s)
        for s in range(6, 16):
            assert bitmap.is_free(s)

    def test_mark_range_free(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        for s in range(1, 16):
            bitmap.set_allocated(s)
        bitmap.mark_range_free(3, 4)
        for s in range(3, 7):
            assert bitmap.is_free(s)
        assert bitmap.is_allocated(2)
        assert bitmap.is_allocated(7)

    def test_mark_range_allocated_overrun(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        with pytest.raises(ValueError, match="extends beyond"):
            bitmap.mark_range_allocated(14, 5)

    def test_mark_range_zero_length(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        with pytest.raises(ValueError, match="must be positive"):
            bitmap.mark_range_allocated(5, 0)


# ---------------------------------------------------------------------------
# CylinderBitmap: serialisation & invariants
# ---------------------------------------------------------------------------


class TestSerialisation:
    def test_to_bytes_is_256(self) -> None:
        assert len(CylinderBitmap.fresh(16).to_bytes()) == BITMAP_SECTOR_SIZE

    def test_round_trip(self) -> None:
        original = CylinderBitmap.fresh(64)
        original.set_allocated(5)
        original.set_allocated(50)
        raw = original.to_bytes()
        reloaded = CylinderBitmap(64, raw)
        assert reloaded == original

    def test_wrong_input_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be 256"):
            CylinderBitmap(16, b"\x00" * 10)

    def test_oversize_cylinder_rejected(self) -> None:
        with pytest.raises(ValueError, match="outside 1..2048"):
            CylinderBitmap(MAX_SECTORS_PER_CYLINDER + 1)

    def test_zero_cylinder_rejected(self) -> None:
        with pytest.raises(ValueError, match="outside 1..2048"):
            CylinderBitmap(0)


class TestOutOfRangeAccess:
    def test_is_free_rejects(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        with pytest.raises(IndexError, match="outside cylinder range"):
            bitmap.is_free(16)

    def test_set_allocated_rejects(self) -> None:
        bitmap = CylinderBitmap.fresh(16)
        with pytest.raises(IndexError):
            bitmap.set_allocated(20)


class TestNonMultipleOfEight:
    """free_count must only count bits within the cylinder range."""

    def test_12_sector_cylinder(self) -> None:
        bitmap = CylinderBitmap.fresh(12)
        assert bitmap.free_count() == 11  # sectors 1..11

    def test_17_sector_cylinder(self) -> None:
        bitmap = CylinderBitmap.fresh(17)
        assert bitmap.free_count() == 16  # sectors 1..16

    def test_stray_high_bits_ignored(self) -> None:
        """A bitmap loaded with junk in unused bits still counts correctly."""
        bitmap = CylinderBitmap.fresh(12)
        raw = bytearray(bitmap.to_bytes())
        raw[1] |= 0xF0  # set bits 12-15 which don't correspond to any sector
        loaded = CylinderBitmap(12, bytes(raw))
        assert loaded.free_count() == 11


# ---------------------------------------------------------------------------
# BitmapShadow
# ---------------------------------------------------------------------------


class _FakeStorage:
    """Simple in-memory backing store for BitmapShadow tests."""

    def __init__(self, num_cylinders: int, sectors_per_cylinder: int) -> None:
        self._spc = sectors_per_cylinder
        self._sectors = {
            c: CylinderBitmap.fresh(sectors_per_cylinder).to_bytes() for c in range(num_cylinders)
        }
        self.read_calls: list[int] = []
        self.write_calls: list[tuple[int, bytes]] = []

    def read(self, cylinder: int) -> bytes:
        self.read_calls.append(cylinder)
        return self._sectors[cylinder]

    def write(self, cylinder: int, data: bytes) -> None:
        self.write_calls.append((cylinder, data))
        self._sectors[cylinder] = data


class TestBitmapShadowLazyLoad:
    def test_reads_on_first_access(self) -> None:
        storage = _FakeStorage(num_cylinders=10, sectors_per_cylinder=16)
        shadow = BitmapShadow(10, 16, storage.read, storage.write)
        assert storage.read_calls == []
        shadow.bitmap_for(3)
        assert storage.read_calls == [3]

    def test_cached_on_second_access(self) -> None:
        storage = _FakeStorage(num_cylinders=10, sectors_per_cylinder=16)
        shadow = BitmapShadow(10, 16, storage.read, storage.write)
        shadow.bitmap_for(3)
        shadow.bitmap_for(3)
        shadow.bitmap_for(3)
        assert storage.read_calls == [3]

    def test_out_of_range_cylinder(self) -> None:
        storage = _FakeStorage(num_cylinders=10, sectors_per_cylinder=16)
        shadow = BitmapShadow(10, 16, storage.read, storage.write)
        with pytest.raises(IndexError):
            shadow.bitmap_for(10)


class TestBitmapShadowFreeCount:
    def test_free_count_matches_bitmap(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        assert shadow.free_count(0) == 15

    def test_total_free(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        assert shadow.total_free() == 3 * 15

    def test_cylinder_with_most_free_initially_zero(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        # All cylinders start with 15 free → picks cylinder 0.
        assert shadow.cylinder_with_most_free() == 0


class TestBitmapShadowMutation:
    def test_mark_allocated_updates_count(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        shadow.mark_allocated(1, 5)
        assert shadow.free_count(1) == 14
        assert shadow.bitmap_for(1).is_allocated(5)

    def test_mark_free_updates_count(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        shadow.mark_allocated(1, 5)
        shadow.mark_free(1, 5)
        assert shadow.free_count(1) == 15

    def test_range_alloc_updates_count(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        shadow.mark_range_allocated(2, 5, 4)
        assert shadow.free_count(2) == 11

    def test_cylinder_with_most_free_after_mutations(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        shadow.mark_range_allocated(0, 1, 10)  # cylinder 0 → 5 free
        shadow.mark_range_allocated(1, 1, 3)  # cylinder 1 → 12 free
        shadow.bitmap_for(2)  # force load → 15 free
        assert shadow.cylinder_with_most_free() == 2


class TestBitmapShadowFlush:
    def test_flush_writes_dirty_only(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        shadow.mark_allocated(1, 5)
        shadow.mark_allocated(2, 3)
        shadow.flush()
        written_cylinders = [c for c, _ in storage.write_calls]
        assert sorted(written_cylinders) == [1, 2]

    def test_flush_clears_dirty_set(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        shadow.mark_allocated(1, 5)
        assert shadow.dirty_cylinders() == frozenset({1})
        shadow.flush()
        assert shadow.dirty_cylinders() == frozenset()

    def test_flush_is_idempotent(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        shadow.mark_allocated(1, 5)
        shadow.flush()
        shadow.flush()
        # Second flush should have been a no-op.
        assert len(storage.write_calls) == 1

    def test_no_op_mutations_are_not_dirty(self) -> None:
        """mark_allocated of already-allocated sector stays clean."""
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        shadow.mark_allocated(1, 0)  # sector 0 is already allocated
        assert shadow.dirty_cylinders() == frozenset()

    def test_round_trip_through_flush(self) -> None:
        storage = _FakeStorage(num_cylinders=3, sectors_per_cylinder=16)
        shadow = BitmapShadow(3, 16, storage.read, storage.write)
        shadow.mark_range_allocated(1, 5, 3)
        shadow.flush()
        # New shadow reading from the same storage should see the same state.
        shadow2 = BitmapShadow(3, 16, storage.read, storage.write)
        for s in range(5, 8):
            assert shadow2.bitmap_for(1).is_allocated(s)

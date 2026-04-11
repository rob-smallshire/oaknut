"""Tests for :class:`oaknut.afs.allocator.Allocator` (phase 8).

The allocator sits on top of :class:`BitmapShadow` and matches the
policy extracted from MAPMAN:

- ``FNDCY`` — cylinder with most free sectors first
  (``Uade11.asm:916-980``)
- ``ALBLK`` — first-fit within a cylinder, low-bit-first
  (``Uade12.asm:520-622``)
- ``FLBLKS`` — spill across cylinders when one can't satisfy
  the whole request (``Uade11.asm:1077``+)
- rollback on insufficient space

Tests build a :class:`BitmapShadow` with a dict-backed
reader/writer, drive the allocator against carefully shaped
free-space layouts, and assert the resulting extents plus the
post-condition that the bitmap shadow's free counts agree with
the original free count minus the allocated total.
"""

from __future__ import annotations

import pytest
from oaknut.afs import AFSInsufficientSpaceError, Allocator
from oaknut.afs.bitmap import BITMAP_SECTOR_SIZE, BitmapShadow, CylinderBitmap
from oaknut.afs.map_sector import Extent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SPC = 16  # small sectors-per-cylinder for clear test layouts
_START_CYL = 100  # absolute cylinder where the AFS region begins


class _DiscBuffer:
    """Dict-backed sector store feeding a :class:`BitmapShadow`.

    Initialises every cylinder's bitmap to "sector 0 allocated,
    sectors 1..N-1 free" — matching what WFSINIT would write on a
    freshly partitioned AFS region.
    """

    def __init__(self, num_cylinders: int) -> None:
        self._sectors: dict[int, bytes] = {}
        self._num_cylinders = num_cylinders
        for cyl in range(num_cylinders):
            bitmap = CylinderBitmap.fresh(_SPC)
            self._sectors[cyl] = bitmap.to_bytes()

    def reader(self, cyl_index: int) -> bytes:
        return self._sectors[cyl_index]

    def writer(self, cyl_index: int, data: bytes) -> None:
        assert len(data) == BITMAP_SECTOR_SIZE
        self._sectors[cyl_index] = data

    def build_shadow(self) -> BitmapShadow:
        return BitmapShadow(
            num_cylinders=self._num_cylinders,
            sectors_per_cylinder=_SPC,
            reader=self.reader,
            writer=self.writer,
        )


def _allocator(num_cylinders: int) -> tuple[Allocator, BitmapShadow, _DiscBuffer]:
    buf = _DiscBuffer(num_cylinders)
    shadow = buf.build_shadow()
    alloc = Allocator(
        shadow,
        start_cylinder=_START_CYL,
        sectors_per_cylinder=_SPC,
    )
    return alloc, shadow, buf


def _absolute(cyl_offset: int, sector_in_cyl: int) -> int:
    """Convert cylinder-within-region index + sector → absolute sector."""
    return (_START_CYL + cyl_offset) * _SPC + sector_in_cyl


# ---------------------------------------------------------------------------
# Construction and sanity
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_valid_construction(self) -> None:
        alloc, shadow, _ = _allocator(num_cylinders=3)
        assert alloc.start_cylinder == _START_CYL
        assert alloc.sectors_per_cylinder == _SPC
        assert alloc.shadow is shadow

    def test_rejects_spc_mismatch(self) -> None:
        _, shadow, _ = _allocator(num_cylinders=3)
        with pytest.raises(ValueError, match="disagrees"):
            Allocator(shadow, start_cylinder=0, sectors_per_cylinder=_SPC + 1)

    def test_total_free_on_fresh_region(self) -> None:
        alloc, _, _ = _allocator(num_cylinders=4)
        # Every cylinder has 15 free sectors (sector 0 is the bitmap).
        assert alloc.total_free_sectors() == 4 * 15


# ---------------------------------------------------------------------------
# Single-cylinder contiguous allocation
# ---------------------------------------------------------------------------


class TestContiguousAllocation:
    def test_allocate_one_sector(self) -> None:
        alloc, shadow, _ = _allocator(num_cylinders=2)
        extents = alloc.allocate(1)
        assert len(extents) == 1
        assert extents[0].length == 1
        # Smallest free bit is sector 1 in whichever cylinder is
        # picked (both have equal free counts; picker returns the
        # first one whose count strictly exceeds the running max,
        # so cylinder 0 wins on tie).
        assert extents[0].start == _absolute(0, 1)
        assert alloc.total_free_sectors() == 2 * 15 - 1

    def test_allocate_whole_cylinder_run(self) -> None:
        alloc, _, _ = _allocator(num_cylinders=2)
        extents = alloc.allocate(15)  # drain cylinder 0 exactly
        assert len(extents) == 1
        assert extents[0] == Extent(start=_absolute(0, 1), length=15)

    def test_allocated_bits_marked_in_bitmap(self) -> None:
        alloc, shadow, _ = _allocator(num_cylinders=1)
        alloc.allocate(5)
        bitmap = shadow.bitmap_for(0)
        assert all(bitmap.is_allocated(s) for s in range(0, 6))
        assert all(bitmap.is_free(s) for s in range(6, 16))


# ---------------------------------------------------------------------------
# Fragmented cylinder — first-fit within a cylinder scans from bit 0
# ---------------------------------------------------------------------------


class TestFragmentedAllocation:
    def _pre_fragment(self, alloc: Allocator) -> None:
        """Pre-allocate an alternating pattern in cylinder 0 of a
        2-cylinder region so that cylinder 0 has free runs at
        sectors 1, 3-4, 6-7, 9-10, 12-13, 15.

        Starting layout is sector 0 allocated, 1..15 free.
        We mark 2, 5, 8, 11, 14 allocated to create the fragments.
        """
        shadow = alloc.shadow
        for sector in (2, 5, 8, 11, 14):
            shadow.mark_allocated(0, sector)

    def test_fragmented_cylinder_produces_multiple_extents(self) -> None:
        alloc, shadow, _ = _allocator(num_cylinders=2)
        self._pre_fragment(alloc)
        # Cylinder 0 free count = 10, cylinder 1 = 15. Picker will
        # choose cylinder 1 first because it has more free. So
        # force the fragmented cylinder to be visited by requesting
        # enough to exhaust cylinder 1 AND draw from cylinder 0.
        # Instead, simpler: drain cylinder 1 to have fewer free
        # than cylinder 0.
        shadow.mark_range_allocated(1, 1, 12)  # cylinder 1 now has 3 free
        # Cylinder 0 free = 10, cylinder 1 free = 3.
        # Request 6 sectors; picker chooses cylinder 0.
        extents = alloc.allocate(6)
        # Expected first-fit scan in cyl 0: sector 1 (1), 3-4 (2),
        # 6-7 (2), 9 (1) → runs of length 1, 2, 2, 1 → 4 extents.
        assert [e.length for e in extents] == [1, 2, 2, 1]
        assert [int(e.start) for e in extents] == [
            _absolute(0, 1),
            _absolute(0, 3),
            _absolute(0, 6),
            _absolute(0, 9),
        ]


# ---------------------------------------------------------------------------
# Cross-cylinder spill — FLBLKS
# ---------------------------------------------------------------------------


class TestCrossCylinderSpill:
    def test_spill_to_next_cylinder(self) -> None:
        alloc, shadow, _ = _allocator(num_cylinders=3)
        # Make cylinder 0 have 20 free (impossible — max 15), so
        # instead: request more than one cylinder can hold.
        # Fresh: each cyl has 15 free. Request 25 → must spill.
        extents = alloc.allocate(25)
        assert sum(e.length for e in extents) == 25
        assert len(extents) == 2  # one per cylinder, contiguous
        # First extent drains one cylinder (15 sectors starting at
        # sector 1 of that cylinder).
        assert extents[0].length == 15
        assert extents[1].length == 10

    def test_spill_chooses_best_cylinder_each_iteration(self) -> None:
        alloc, shadow, _ = _allocator(num_cylinders=3)
        # Set up uneven free counts:
        #   cyl 0: 5 free  (mark 10 allocated)
        #   cyl 1: 15 free (default)
        #   cyl 2: 10 free (mark 5 allocated)
        shadow.mark_range_allocated(0, 1, 10)  # cyl 0: 5 free
        shadow.mark_range_allocated(2, 1, 5)  # cyl 2: 10 free
        extents = alloc.allocate(22)
        # First pick: cyl 1 (15 free) → 15 sectors.
        # Next: cyl 2 (10 free) → 7 sectors.
        # Total 22 ✓.
        assert sum(e.length for e in extents) == 22
        # Verify the starts come from cyl 1 then cyl 2, not cyl 0.
        first_cyl_abs = int(extents[0].start) // _SPC - _START_CYL
        second_cyl_abs = int(extents[1].start) // _SPC - _START_CYL
        assert first_cyl_abs == 1
        assert second_cyl_abs == 2

    def test_exact_drain_of_every_cylinder(self) -> None:
        alloc, _, _ = _allocator(num_cylinders=4)
        total = alloc.total_free_sectors()
        extents = alloc.allocate(total)
        assert sum(e.length for e in extents) == total
        assert alloc.total_free_sectors() == 0


# ---------------------------------------------------------------------------
# Insufficient space → rollback
# ---------------------------------------------------------------------------


class TestInsufficientSpace:
    def test_request_exceeds_free_raises(self) -> None:
        alloc, _, _ = _allocator(num_cylinders=2)
        with pytest.raises(AFSInsufficientSpaceError, match="short by"):
            alloc.allocate(100)

    def test_failed_allocation_rolls_back_partial_extents(self) -> None:
        alloc, shadow, _ = _allocator(num_cylinders=2)
        before = alloc.total_free_sectors()
        with pytest.raises(AFSInsufficientSpaceError):
            alloc.allocate(before + 1)
        assert alloc.total_free_sectors() == before
        # And every cylinder should be back to its fresh state.
        for cyl in range(2):
            bitmap = shadow.bitmap_for(cyl)
            assert bitmap.is_allocated(0)  # bitmap sector itself
            for sector in range(1, _SPC):
                assert bitmap.is_free(sector)

    def test_zero_request_rejected(self) -> None:
        alloc, _, _ = _allocator(num_cylinders=1)
        with pytest.raises(ValueError, match="positive"):
            alloc.allocate(0)


# ---------------------------------------------------------------------------
# allocate_sector — ALBLK single-sector case
# ---------------------------------------------------------------------------


class TestAllocateSector:
    def test_returns_single_sin(self) -> None:
        alloc, _, _ = _allocator(num_cylinders=1)
        sin = alloc.allocate_sector()
        assert int(sin) == _absolute(0, 1)

    def test_each_call_advances(self) -> None:
        alloc, _, _ = _allocator(num_cylinders=1)
        sins = [int(alloc.allocate_sector()) for _ in range(4)]
        assert sins == [
            _absolute(0, 1),
            _absolute(0, 2),
            _absolute(0, 3),
            _absolute(0, 4),
        ]


# ---------------------------------------------------------------------------
# Freeing
# ---------------------------------------------------------------------------


class TestFreeExtent:
    def test_free_single_extent_restores_count(self) -> None:
        alloc, _, _ = _allocator(num_cylinders=2)
        before = alloc.total_free_sectors()
        extents = alloc.allocate(5)
        assert alloc.total_free_sectors() == before - 5
        alloc.free_extents(extents)
        assert alloc.total_free_sectors() == before

    def test_free_then_reallocate_reuses_sectors(self) -> None:
        alloc, _, _ = _allocator(num_cylinders=1)
        first = alloc.allocate(3)
        alloc.free_extents(first)
        second = alloc.allocate(3)
        assert [int(e.start) for e in second] == [int(e.start) for e in first]

    def test_free_extent_spanning_cylinders(self) -> None:
        alloc, shadow, _ = _allocator(num_cylinders=3)
        # Allocate 25 sectors — will straddle cylinder 0 and 1.
        extents = alloc.allocate(25)
        total_before_free = alloc.total_free_sectors()
        alloc.free_extents(extents)
        assert alloc.total_free_sectors() == total_before_free + 25

    def test_free_sector_single(self) -> None:
        alloc, _, _ = _allocator(num_cylinders=1)
        sin = alloc.allocate_sector()
        alloc.free_sector(sin)
        assert alloc.total_free_sectors() == 15

    def test_dirty_set_includes_touched_cylinders(self) -> None:
        alloc, shadow, _ = _allocator(num_cylinders=3)
        alloc.allocate(20)  # spans cyl 0 and 1
        dirty = shadow.dirty_cylinders()
        assert 0 in dirty and 1 in dirty


# ---------------------------------------------------------------------------
# Flush round-trip — end-to-end write of dirty bitmaps
# ---------------------------------------------------------------------------


class TestFlushRoundTrip:
    def test_flush_persists_allocations_to_writer(self) -> None:
        buf = _DiscBuffer(num_cylinders=2)
        shadow = buf.build_shadow()
        alloc = Allocator(shadow, start_cylinder=_START_CYL, sectors_per_cylinder=_SPC)
        alloc.allocate(5)
        shadow.flush()
        # Re-load from the persisted bytes and verify allocation
        # state survived.
        shadow2 = buf.build_shadow()
        bitmap0 = shadow2.bitmap_for(0)
        assert bitmap0.allocated_count() == 6  # sector 0 (bitmap) + 5 allocated
        for sector in range(0, 6):
            assert bitmap0.is_allocated(sector)

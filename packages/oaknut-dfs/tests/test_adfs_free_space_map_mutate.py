"""Tests for ADFS old-format free space map mutation.

Tests for allocating and freeing sectors in the old free space map,
including checksum recalculation and entry merging.
"""

import pytest

from helpers.adfs_image import make_old_free_space_map as _make_old_free_space_map
from oaknut_dfs.adfs_free_space_map import OldFreeSpaceMap
from oaknut_dfs.exceptions import ADFSDiscFullError
from oaknut_dfs.sectors_view import SectorsView


def _make_fsm(free_entries, disc_size_sectors=640, **kwargs):
    """Build an OldFreeSpaceMap from free entry specs."""
    fsm_bytes = _make_old_free_space_map(
        free_entries, disc_size_sectors=disc_size_sectors, **kwargs
    )
    view = SectorsView([memoryview(fsm_bytes)])
    return OldFreeSpaceMap(view)


class TestAllocate:

    def test_allocate_from_single_entry(self):
        """Allocate from a disc with one free region."""
        fsm = _make_fsm([(7, 633)])
        start = fsm.allocate(10)
        assert start == 7
        # Free space reduced
        entries = fsm.free_space_entries()
        assert len(entries) == 1
        assert entries[0] == (17 * 256, 623 * 256)

    def test_allocate_exact_fit(self):
        """Allocating exactly the free region size removes the entry."""
        fsm = _make_fsm([(7, 10)])
        start = fsm.allocate(10)
        assert start == 7
        assert fsm.num_entries == 0
        assert fsm.free_space == 0

    def test_allocate_single_sector(self):
        fsm = _make_fsm([(7, 633)])
        start = fsm.allocate(1)
        assert start == 7
        entries = fsm.free_space_entries()
        assert entries[0] == (8 * 256, 632 * 256)

    def test_allocate_from_first_fit(self):
        """With multiple free regions, allocate from the first that fits."""
        fsm = _make_fsm([(7, 5), (20, 100), (200, 50)])
        start = fsm.allocate(10)
        assert start == 20
        entries = fsm.free_space_entries()
        assert len(entries) == 3
        assert entries[0] == (7 * 256, 5 * 256)
        assert entries[1] == (30 * 256, 90 * 256)
        assert entries[2] == (200 * 256, 50 * 256)

    def test_allocate_from_first_entry_when_fits(self):
        """First-fit: use the first entry if it's big enough."""
        fsm = _make_fsm([(7, 100), (200, 50)])
        start = fsm.allocate(10)
        assert start == 7

    def test_allocate_too_large_raises(self):
        """Allocating more than any single free region raises."""
        fsm = _make_fsm([(7, 5), (20, 10)])
        with pytest.raises(ADFSDiscFullError, match="[Nn]o free space"):
            fsm.allocate(11)

    def test_allocate_from_empty_map_raises(self):
        fsm = _make_fsm([])
        with pytest.raises(ADFSDiscFullError, match="[Nn]o free space"):
            fsm.allocate(1)

    def test_allocate_zero_raises(self):
        fsm = _make_fsm([(7, 633)])
        with pytest.raises(ValueError):
            fsm.allocate(0)

    def test_allocate_negative_raises(self):
        fsm = _make_fsm([(7, 633)])
        with pytest.raises(ValueError):
            fsm.allocate(-1)

    def test_allocate_preserves_valid_checksums(self):
        fsm = _make_fsm([(7, 633)])
        fsm.allocate(10)
        assert fsm.validate() == []

    def test_multiple_allocations(self):
        fsm = _make_fsm([(7, 633)])
        s1 = fsm.allocate(5)
        s2 = fsm.allocate(3)
        s3 = fsm.allocate(10)
        assert s1 == 7
        assert s2 == 12
        assert s3 == 15
        assert fsm.free_space == (633 - 18) * 256

    def test_allocate_removes_entry_and_shifts(self):
        """When an exact-fit entry is removed, subsequent entries shift down."""
        fsm = _make_fsm([(7, 5), (20, 5), (30, 100)])
        start = fsm.allocate(5)  # Takes first entry exactly
        assert start == 7
        assert fsm.num_entries == 2
        entries = fsm.free_space_entries()
        assert entries[0] == (20 * 256, 5 * 256)
        assert entries[1] == (30 * 256, 100 * 256)


class TestFree:

    def test_free_adds_entry(self):
        """Freeing sectors adds a new free space entry."""
        fsm = _make_fsm([(20, 100)])
        fsm.free(7, 5)
        assert fsm.num_entries == 2

    def test_free_merge_before(self):
        """Freeing sectors immediately before an existing entry merges them."""
        fsm = _make_fsm([(20, 100)])
        fsm.free(15, 5)
        entries = fsm.free_space_entries()
        assert len(entries) == 1
        assert entries[0] == (15 * 256, 105 * 256)

    def test_free_merge_after(self):
        """Freeing sectors immediately after an existing entry merges them."""
        fsm = _make_fsm([(20, 100)])
        fsm.free(120, 5)
        entries = fsm.free_space_entries()
        assert len(entries) == 1
        assert entries[0] == (20 * 256, 105 * 256)

    def test_free_merge_both(self):
        """Freeing sectors that bridge two free regions merges all three."""
        fsm = _make_fsm([(10, 5), (20, 100)])
        fsm.free(15, 5)
        entries = fsm.free_space_entries()
        assert len(entries) == 1
        assert entries[0] == (10 * 256, 110 * 256)

    def test_free_no_merge(self):
        """Freeing sectors not adjacent to any entry creates a new one."""
        fsm = _make_fsm([(20, 100)])
        fsm.free(7, 3)
        entries = fsm.free_space_entries()
        assert len(entries) == 2
        # New entry should be inserted in order
        assert entries[0] == (7 * 256, 3 * 256)
        assert entries[1] == (20 * 256, 100 * 256)

    def test_free_preserves_valid_checksums(self):
        fsm = _make_fsm([(20, 100)])
        fsm.free(7, 5)
        assert fsm.validate() == []

    def test_free_zero_raises(self):
        fsm = _make_fsm([(20, 100)])
        with pytest.raises(ValueError):
            fsm.free(7, 0)

    def test_free_negative_raises(self):
        fsm = _make_fsm([(20, 100)])
        with pytest.raises(ValueError):
            fsm.free(7, -1)

    def test_free_into_empty_map(self):
        fsm = _make_fsm([])
        fsm.free(7, 10)
        entries = fsm.free_space_entries()
        assert len(entries) == 1
        assert entries[0] == (7 * 256, 10 * 256)

    def test_free_maintains_sorted_order(self):
        """Freed entries are inserted in start-address order."""
        fsm = _make_fsm([(10, 5), (100, 50)])
        fsm.free(50, 10)
        entries = fsm.free_space_entries()
        assert len(entries) == 3
        assert entries[0] == (10 * 256, 5 * 256)
        assert entries[1] == (50 * 256, 10 * 256)
        assert entries[2] == (100 * 256, 50 * 256)


class TestAllocateAndFreeRoundTrip:

    def test_allocate_then_free_restores_state(self):
        """Allocate then free should restore the original free space."""
        fsm = _make_fsm([(7, 633)])
        original_free = fsm.free_space
        start = fsm.allocate(10)
        fsm.free(start, 10)
        assert fsm.free_space == original_free
        assert fsm.validate() == []

    def test_allocate_free_allocate(self):
        """Freed space can be reused by subsequent allocation."""
        fsm = _make_fsm([(7, 633)])
        s1 = fsm.allocate(10)
        assert s1 == 7
        s2 = fsm.allocate(5)
        assert s2 == 17
        fsm.free(s1, 10)  # Free the first allocation
        s3 = fsm.allocate(8)  # Should reuse the freed space
        assert s3 == 7

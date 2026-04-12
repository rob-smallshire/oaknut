"""Phase 10 — directory auto-grow via the allocator.

Covers both the byte-level helper (``grow_directory_bytes``) and
the end-to-end ``AFS.insert_into_directory`` path that extends the
underlying object's map chain when the free list is empty.
"""

from __future__ import annotations

import datetime

import pytest
from helpers.afs_image import build_synthetic_adfs_with_afs
from oaknut.afs import (
    AFSAccess,
    AfsDate,
    AFSDirectoryFullError,
    SystemInternalName,
)
from oaknut.afs.directory import (
    AfsDirectory,
    DirectoryEntry,
    build_directory_bytes,
    grow_directory_bytes,
    insert_entry,
)


def _date() -> AfsDate:
    return AfsDate(datetime.date(2026, 4, 11))


def _entry(name: str, sin: int = 0x200) -> DirectoryEntry:
    return DirectoryEntry(
        name=name,
        load_address=0x11223344,
        exec_address=0x55667788,
        access=AFSAccess.from_string("LR/R"),
        date=_date(),
        sin=SystemInternalName(sin),
    )


# ---------------------------------------------------------------------------
# grow_directory_bytes unit tests
# ---------------------------------------------------------------------------


class TestGrowDirectoryBytes:
    def test_grow_empty_directory_adds_slots_to_free_list(self) -> None:
        raw = build_directory_bytes("$", 0, [], 512)
        grown = grow_directory_bytes(raw, 768)
        parsed = AfsDirectory.from_bytes(grown)
        # 768 - 18 = 750, 750 // 26 = 28 slots
        assert parsed.capacity == 28
        assert len(parsed) == 0

    def test_grow_preserves_existing_entries(self) -> None:
        entries = [_entry(f"E{i:02d}", sin=0x100 + i) for i in range(5)]
        raw = build_directory_bytes("$", 0, entries, 512)
        grown = grow_directory_bytes(raw, 768)
        parsed = AfsDirectory.from_bytes(grown)
        names = sorted(e.name for e in parsed)
        assert names == ["E00", "E01", "E02", "E03", "E04"]

    def test_grow_bumps_sequence_number(self) -> None:
        raw = build_directory_bytes("$", 0x42, [], 512)
        grown = grow_directory_bytes(raw, 768)
        assert AfsDirectory.from_bytes(grown).master_sequence_number == 0x43

    def test_grow_allows_subsequent_inserts(self) -> None:
        entries = [_entry(f"E{i:02d}", sin=0x100 + i) for i in range(19)]
        raw = build_directory_bytes("$", 0, entries, 512)
        # Confirm it's full.
        with pytest.raises(AFSDirectoryFullError):
            insert_entry(raw, _entry("Extra"))
        grown = grow_directory_bytes(raw, 768)
        # Now we can insert at least 9 more entries (1 sector worth
        # of 26-byte slots = 9 full slots).
        for i in range(9):
            grown = insert_entry(grown, _entry(f"Fresh{i}", sin=0xA00 + i))
        parsed = AfsDirectory.from_bytes(grown)
        assert len(parsed) == 19 + 9

    def test_grow_rejects_zero_delta(self) -> None:
        raw = build_directory_bytes("$", 0, [], 512)
        with pytest.raises(ValueError, match="must exceed"):
            grow_directory_bytes(raw, 512)

    def test_grow_rejects_non_sector_multiple(self) -> None:
        raw = build_directory_bytes("$", 0, [], 512)
        with pytest.raises(ValueError, match="multiple of 256"):
            grow_directory_bytes(raw, 513)

    def test_grow_trailing_and_leading_seq_match(self) -> None:
        raw = build_directory_bytes("$", 0, [], 512)
        grown = grow_directory_bytes(raw, 768)
        assert grown[2] == grown[-1]


# ---------------------------------------------------------------------------
# End-to-end AFS.insert_into_directory
# ---------------------------------------------------------------------------


def _insert_n_files(afs, n: int) -> None:
    """Insert ``n`` files into the root directory."""
    root_sin = afs.info_sector.root_sin
    for i in range(n):
        afs.insert_into_directory(
            root_sin,
            DirectoryEntry(
                name=f"New{i:03d}",
                load_address=0x1000 + i,
                exec_address=0x2000 + i,
                access=AFSAccess.from_string("LR/R"),
                date=_date(),
                # Use synthetic SINs that don't conflict with the
                # pre-existing objects in the synthetic image. The
                # insert doesn't validate SINs, so these can be
                # arbitrary placeholders.
                sin=SystemInternalName(0x10000 + i),
            ),
        )


class TestInsertIntoDirectoryAutoGrow:
    def test_insert_under_capacity_no_grow(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        _insert_n_files(afs, 5)
        names = [p.name for p in afs.root]
        for i in range(5):
            assert f"New{i:03d}" in names

    def test_insert_triggers_grow_beyond_default_capacity(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        # The synthetic image starts with Hello + Passwords + room;
        # the default 2-sector dir holds 19. Insert 25 fresh entries
        # — growth must happen.
        _insert_n_files(afs, 25)
        names = [p.name for p in afs.root]
        for i in range(25):
            assert f"New{i:03d}" in names, f"missing New{i:03d}"

    def test_grown_directory_survives_reread(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        _insert_n_files(afs, 25)
        afs.flush()
        # Fetch a fresh AFS handle against the same ADFS.
        afs2 = adfs.afs_partition
        names = [p.name for p in afs2.root]
        for i in range(25):
            assert f"New{i:03d}" in names

    def test_growth_increases_underlying_object_size(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        root_sin = afs.info_sector.root_sin
        size_before = len(afs._read_object_bytes(root_sin))
        _insert_n_files(afs, 25)
        size_after = len(afs._read_object_bytes(root_sin))
        assert size_after > size_before
        # Growth is in 256-byte steps.
        assert (size_after - size_before) % 256 == 0

    def test_many_inserts_eventually_hit_maxdir(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        # Insert up to ~250 entries; somewhere near 255 we should
        # hit MAXDIR. We don't test the exact boundary because the
        # starting directory already has entries, but we verify the
        # cap is enforced before we exceed it.
        inserted = 0
        try:
            for i in range(260):
                afs.insert_into_directory(
                    afs.info_sector.root_sin,
                    DirectoryEntry(
                        name=f"X{i:03d}",
                        load_address=0,
                        exec_address=0,
                        access=AFSAccess.from_string("LR/R"),
                        date=_date(),
                        sin=SystemInternalName(0x20000 + i),
                    ),
                )
                inserted += 1
        except AFSDirectoryFullError:
            pass
        # Should have inserted many, but not all 260.
        assert inserted > 200
        assert inserted < 260

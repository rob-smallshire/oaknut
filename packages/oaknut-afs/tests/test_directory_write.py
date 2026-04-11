"""Phase 9 — byte-level mutation of AFS directories.

These tests drive :func:`insert_entry`, :func:`delete_entry`,
:func:`rename_entry`, and :func:`update_entry_fields` against
hand-built directory buffers, asserting that:

- The parsed view after mutation matches the expected entry list.
- The master sequence number is bumped on every mutation (both
  leading and trailing copies).
- The in-use linked list remains navigable from ``DRFRST`` to the
  end, and the reader's walk returns entries in the order threaded
  by the list (which is alphabetical after insert/delete but may
  become un-sorted after rename — by design).
- The free list is correctly re-threaded on both insert (pop head)
  and delete (prepend head).
- Round-tripping through parse→mutate→reparse is idempotent for
  every single-operation case.

The agents' framing mirrors DIRMAN's RETANP / DRDELT / RETAIN paths
in the ROM. Citations are in the ``directory.py`` module docstring
and in the L3V126 ``comments`` branch.
"""

from __future__ import annotations

import datetime

import pytest
from oaknut.afs import (
    AFSAccess,
    AfsDate,
    AFSDirectoryEntryExistsError,
    AFSDirectoryEntryNotFoundError,
    AFSDirectoryFullError,
    SystemInternalName,
)
from oaknut.afs.directory import (
    AfsDirectory,
    DirectoryEntry,
    build_directory_bytes,
    delete_entry,
    insert_entry,
    rename_entry,
    update_entry_fields,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _date() -> AfsDate:
    return AfsDate(datetime.date(2026, 4, 11))


def _entry(name: str, sin: int = 0x200, access: str = "LR/R") -> DirectoryEntry:
    return DirectoryEntry(
        name=name,
        load_address=0x11223344,
        exec_address=0x55667788,
        access=AFSAccess.from_string(access),
        date=_date(),
        sin=SystemInternalName(sin),
    )


def _build(
    entries: list[DirectoryEntry],
    *,
    master_seq: int = 0x10,
    size: int = 512,
) -> bytes:
    return build_directory_bytes(
        name="$",
        master_sequence_number=master_seq,
        entries=entries,
        size_in_bytes=size,
    )


def _parse(raw: bytes) -> AfsDirectory:
    return AfsDirectory.from_bytes(raw)


# ---------------------------------------------------------------------------
# Insertion
# ---------------------------------------------------------------------------


class TestInsertEntry:
    def test_insert_into_empty_directory(self) -> None:
        raw = _build([], master_seq=5)
        new_raw = insert_entry(raw, _entry("Hello", sin=0x300))
        parsed = _parse(new_raw)
        assert [e.name for e in parsed] == ["Hello"]
        assert parsed[0].sin == 0x300
        assert parsed.master_sequence_number == 6

    def test_insert_preserves_alphabetical_order(self) -> None:
        raw = _build([_entry("Alpha"), _entry("Gamma")])
        new_raw = insert_entry(raw, _entry("Beta", sin=0x400))
        names = [e.name for e in _parse(new_raw)]
        assert names == ["Alpha", "Beta", "Gamma"]

    def test_insert_at_head(self) -> None:
        raw = _build([_entry("Beta"), _entry("Gamma")])
        new_raw = insert_entry(raw, _entry("Alpha"))
        assert [e.name for e in _parse(new_raw)] == ["Alpha", "Beta", "Gamma"]

    def test_insert_at_tail(self) -> None:
        raw = _build([_entry("Alpha"), _entry("Beta")])
        new_raw = insert_entry(raw, _entry("Gamma"))
        assert [e.name for e in _parse(new_raw)] == ["Alpha", "Beta", "Gamma"]

    def test_insert_bumps_sequence_number(self) -> None:
        raw = _build([], master_seq=0x42)
        new_raw = insert_entry(raw, _entry("X"))
        assert _parse(new_raw).master_sequence_number == 0x43

    def test_insert_sequence_wraps_at_ff(self) -> None:
        raw = _build([], master_seq=0xFF)
        new_raw = insert_entry(raw, _entry("X"))
        assert _parse(new_raw).master_sequence_number == 0x00

    def test_insert_duplicate_name_rejected(self) -> None:
        raw = _build([_entry("Alpha")])
        with pytest.raises(AFSDirectoryEntryExistsError, match="Alpha"):
            insert_entry(raw, _entry("Alpha", sin=0x999))

    def test_insert_duplicate_case_insensitive(self) -> None:
        raw = _build([_entry("Alpha")])
        with pytest.raises(AFSDirectoryEntryExistsError):
            insert_entry(raw, _entry("ALPHA"))

    def test_insert_into_full_directory_raises(self) -> None:
        # A 512-byte directory holds 19 slots. Fill it.
        entries = [_entry(f"E{i:02d}", sin=0x100 + i) for i in range(19)]
        raw = _build(entries)
        with pytest.raises(AFSDirectoryFullError, match="no free slots"):
            insert_entry(raw, _entry("Extra"))

    def test_insert_multiple_sequential(self) -> None:
        raw = _build([])
        # Insert 5 entries in random-ish order; expect alphabetical walk.
        for name in ("Eve", "Alice", "Dave", "Bob", "Carol"):
            raw = insert_entry(raw, _entry(name, sin=ord(name[0])))
        names = [e.name for e in _parse(raw)]
        assert names == ["Alice", "Bob", "Carol", "Dave", "Eve"]

    def test_insert_preserves_other_entries_fields(self) -> None:
        original = [_entry("Alpha", sin=0x111)]
        raw = _build(original)
        new_raw = insert_entry(raw, _entry("Beta", sin=0x222))
        parsed = _parse(new_raw)
        alpha = parsed["Alpha"]
        assert alpha.sin == 0x111
        assert alpha.load_address == 0x11223344


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


class TestDeleteEntry:
    def test_delete_single_entry(self) -> None:
        raw = _build([_entry("OnlyOne")])
        new_raw = delete_entry(raw, "OnlyOne")
        parsed = _parse(new_raw)
        assert len(parsed) == 0
        assert parsed.master_sequence_number == 0x11

    def test_delete_head_entry(self) -> None:
        raw = _build([_entry("Alpha"), _entry("Beta"), _entry("Gamma")])
        new_raw = delete_entry(raw, "Alpha")
        assert [e.name for e in _parse(new_raw)] == ["Beta", "Gamma"]

    def test_delete_middle_entry(self) -> None:
        raw = _build([_entry("Alpha"), _entry("Beta"), _entry("Gamma")])
        new_raw = delete_entry(raw, "Beta")
        assert [e.name for e in _parse(new_raw)] == ["Alpha", "Gamma"]

    def test_delete_tail_entry(self) -> None:
        raw = _build([_entry("Alpha"), _entry("Beta"), _entry("Gamma")])
        new_raw = delete_entry(raw, "Gamma")
        assert [e.name for e in _parse(new_raw)] == ["Alpha", "Beta"]

    def test_delete_bumps_sequence_number(self) -> None:
        raw = _build([_entry("Solo")], master_seq=0x7F)
        new_raw = delete_entry(raw, "Solo")
        assert _parse(new_raw).master_sequence_number == 0x80

    def test_delete_missing_entry_raises(self) -> None:
        raw = _build([_entry("Alpha")])
        with pytest.raises(AFSDirectoryEntryNotFoundError, match="Missing"):
            delete_entry(raw, "Missing")

    def test_delete_is_case_insensitive(self) -> None:
        raw = _build([_entry("Alpha")])
        new_raw = delete_entry(raw, "ALPHA")
        assert len(_parse(new_raw)) == 0

    def test_deleted_slot_goes_to_free_list(self) -> None:
        # Delete and immediately re-insert a new entry with a
        # different name; it should succeed because the free list
        # received the just-deleted slot.
        raw = _build([_entry("Alpha"), _entry("Beta")])
        raw = delete_entry(raw, "Alpha")
        raw = insert_entry(raw, _entry("Gamma"))
        assert [e.name for e in _parse(raw)] == ["Beta", "Gamma"]

    def test_delete_all_then_insert(self) -> None:
        raw = _build([_entry("One"), _entry("Two"), _entry("Three")])
        for name in ("One", "Two", "Three"):
            raw = delete_entry(raw, name)
        raw = insert_entry(raw, _entry("Brand"))
        assert [e.name for e in _parse(raw)] == ["Brand"]


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


class TestRenameEntry:
    def test_rename_within_sort_position(self) -> None:
        # Alpha → Alphb: sort position unchanged, list stays sorted.
        raw = _build([_entry("Alpha"), _entry("Beta"), _entry("Gamma")])
        new_raw = rename_entry(raw, "Alpha", "Alphb")
        assert [e.name for e in _parse(new_raw)] == ["Alphb", "Beta", "Gamma"]

    def test_rename_preserves_sin_and_addresses(self) -> None:
        raw = _build([_entry("Alpha", sin=0x999)])
        new_raw = rename_entry(raw, "Alpha", "Beta")
        parsed = _parse(new_raw)
        assert parsed[0].name == "Beta"
        assert parsed[0].sin == 0x999
        assert parsed[0].load_address == 0x11223344

    def test_rename_bumps_sequence_number(self) -> None:
        raw = _build([_entry("X")], master_seq=0x10)
        new_raw = rename_entry(raw, "X", "Y")
        assert _parse(new_raw).master_sequence_number == 0x11

    def test_rename_to_existing_name_rejected(self) -> None:
        raw = _build([_entry("Alpha"), _entry("Beta")])
        with pytest.raises(AFSDirectoryEntryExistsError):
            rename_entry(raw, "Alpha", "Beta")

    def test_rename_missing_entry_rejected(self) -> None:
        raw = _build([_entry("Alpha")])
        with pytest.raises(AFSDirectoryEntryNotFoundError):
            rename_entry(raw, "Ghost", "NewName")

    def test_rename_to_same_name_is_touch(self) -> None:
        raw = _build([_entry("Alpha")], master_seq=0x50)
        new_raw = rename_entry(raw, "Alpha", "Alpha")
        parsed = _parse(new_raw)
        assert [e.name for e in parsed] == ["Alpha"]
        assert parsed.master_sequence_number == 0x51

    def test_in_place_rename_can_leave_list_unsorted(self) -> None:
        # ROM-faithful: renaming "Alpha" to "Zulu" leaves the entry
        # at its original list position even though "Zulu" is after
        # "Beta" and "Gamma" alphabetically. The walk still visits
        # in link order. The parser does not re-sort.
        raw = _build([_entry("Alpha"), _entry("Beta"), _entry("Gamma")])
        new_raw = rename_entry(raw, "Alpha", "Zulu")
        walk_order = [e.name for e in _parse(new_raw)]
        # The first visited entry is still the one at the original
        # "Alpha" slot position — now named "Zulu" — because the
        # header's DRFRST still points there and its DRLINK still
        # threads to the former "Beta".
        assert walk_order[0] == "Zulu"
        assert set(walk_order) == {"Zulu", "Beta", "Gamma"}


# ---------------------------------------------------------------------------
# Update fields (the duplicate-insert overwrite path)
# ---------------------------------------------------------------------------


class TestUpdateEntryFields:
    def test_update_sin(self) -> None:
        raw = _build([_entry("Alpha", sin=0x100)])
        new_raw = update_entry_fields(raw, "Alpha", sin=SystemInternalName(0x900))
        assert _parse(new_raw)["Alpha"].sin == 0x900

    def test_update_load_and_exec(self) -> None:
        raw = _build([_entry("Alpha")])
        new_raw = update_entry_fields(
            raw, "Alpha", load_address=0xFFFF0000, exec_address=0xDEADBEEF
        )
        parsed = _parse(new_raw)["Alpha"]
        assert parsed.load_address == 0xFFFF0000
        assert parsed.exec_address == 0xDEADBEEF

    def test_update_preserves_name_and_access(self) -> None:
        raw = _build([_entry("Alpha", access="LR/R")])
        new_raw = update_entry_fields(raw, "Alpha", sin=SystemInternalName(0xAA))
        entry = _parse(new_raw)["Alpha"]
        assert entry.name == "Alpha"
        # Access preserved
        assert entry.access.to_byte() == AFSAccess.from_string("LR/R").to_byte()

    def test_update_missing_entry_raises(self) -> None:
        raw = _build([_entry("Alpha")])
        with pytest.raises(AFSDirectoryEntryNotFoundError):
            update_entry_fields(raw, "Ghost", sin=SystemInternalName(1))

    def test_update_bumps_sequence_number(self) -> None:
        raw = _build([_entry("X")], master_seq=0x20)
        new_raw = update_entry_fields(raw, "X", sin=SystemInternalName(0xBB))
        assert _parse(new_raw).master_sequence_number == 0x21


# ---------------------------------------------------------------------------
# Trailing sequence number consistency
# ---------------------------------------------------------------------------


class TestSequenceNumberInvariant:
    def test_leading_and_trailing_always_match_after_insert(self) -> None:
        raw = _build([])
        new_raw = insert_entry(raw, _entry("A"))
        assert new_raw[2] == new_raw[-1]

    def test_leading_and_trailing_always_match_after_delete(self) -> None:
        raw = _build([_entry("A"), _entry("B")])
        new_raw = delete_entry(raw, "A")
        assert new_raw[2] == new_raw[-1]

    def test_leading_and_trailing_always_match_after_rename(self) -> None:
        raw = _build([_entry("A")])
        new_raw = rename_entry(raw, "A", "B")
        assert new_raw[2] == new_raw[-1]


# ---------------------------------------------------------------------------
# Free-list reuse — exhaust then replenish
# ---------------------------------------------------------------------------


class TestFreeListDynamics:
    def test_fill_then_delete_then_fill(self) -> None:
        raw = _build([])
        # Fill 19 slots (default 2-sector capacity).
        for i in range(19):
            raw = insert_entry(raw, _entry(f"E{i:02d}", sin=0x100 + i))
        # Confirm full — next insert fails.
        with pytest.raises(AFSDirectoryFullError):
            insert_entry(raw, _entry("Extra"))
        # Delete one, then insert succeeds.
        raw = delete_entry(raw, "E05")
        raw = insert_entry(raw, _entry("NewOne", sin=0x200))
        names = [e.name for e in _parse(raw)]
        assert "NewOne" in names
        assert "E05" not in names
        assert len(names) == 19

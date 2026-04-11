"""Tests for oaknut.afs.directory — read path.

Covers header parsing, in-use list traversal, alphabetical order,
the slot-fill-from-end layout the server uses, master-sequence-number
validation, bad-input handling, and the ``build_directory_bytes``
helper that tests use to construct fixtures.
"""

from __future__ import annotations

import datetime

import pytest
from oaknut.afs import AFSAccess, AFSBrokenDirectoryError, AfsDate, SystemInternalName
from oaknut.afs.directory import (
    ENTRY_SIZE,
    HEADER_SIZE,
    MAX_ENTRIES,
    MAX_NAME_LENGTH,
    MIN_DIRECTORY_SIZE,
    AfsDirectory,
    DirectoryEntry,
    build_directory_bytes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_date() -> AfsDate:
    return AfsDate(datetime.date(2024, 6, 15))


def _file_entry(name: str, sin: int, access: str = "LR/R") -> DirectoryEntry:
    return DirectoryEntry(
        name=name,
        load_address=0x12345678,
        exec_address=0x9ABCDEF0,
        access=AFSAccess.from_string(access),
        date=_sample_date(),
        sin=SystemInternalName(sin),
    )


def _dir_entry(name: str, sin: int, access: str = "DL/") -> DirectoryEntry:
    return DirectoryEntry(
        name=name,
        load_address=0,
        exec_address=0,
        access=AFSAccess.from_string(access),
        date=_sample_date(),
        sin=SystemInternalName(sin),
    )


# ---------------------------------------------------------------------------
# Empty directory
# ---------------------------------------------------------------------------


class TestEmptyDirectory:
    def test_parses(self) -> None:
        raw = build_directory_bytes("$", 0, [], 512)
        parsed = AfsDirectory.from_bytes(raw)
        assert parsed.name == "$"
        assert len(parsed) == 0
        assert parsed.capacity == 19  # default 2-sector directory

    def test_len_zero(self) -> None:
        raw = build_directory_bytes("$", 0, [], 512)
        assert len(AfsDirectory.from_bytes(raw)) == 0

    def test_iter_empty(self) -> None:
        raw = build_directory_bytes("$", 0, [], 512)
        assert list(AfsDirectory.from_bytes(raw)) == []

    def test_master_seq_round_trip(self) -> None:
        raw = build_directory_bytes("$", 42, [], 512)
        assert AfsDirectory.from_bytes(raw).master_sequence_number == 42


# ---------------------------------------------------------------------------
# Single-entry directory
# ---------------------------------------------------------------------------


class TestSingleEntry:
    def test_one_entry_round_trip(self) -> None:
        entry = _file_entry("HELLO", 0x100)
        raw = build_directory_bytes("$", 0, [entry], 512)
        parsed = AfsDirectory.from_bytes(raw)
        assert len(parsed) == 1
        assert parsed[0].name == "HELLO"
        assert parsed[0].sin == 0x100
        assert parsed[0].access.to_string() == "LR/R"
        assert parsed[0].load_address == 0x12345678
        assert parsed[0].exec_address == 0x9ABCDEF0
        assert parsed[0].date.date == datetime.date(2024, 6, 15)

    def test_find_by_name(self) -> None:
        entry = _file_entry("README", 0x200)
        raw = build_directory_bytes("$", 0, [entry], 512)
        found = AfsDirectory.from_bytes(raw).find("README")
        assert found.sin == 0x200

    def test_find_case_insensitive(self) -> None:
        entry = _file_entry("Readme", 0x200)
        raw = build_directory_bytes("$", 0, [entry], 512)
        assert AfsDirectory.from_bytes(raw).find("README").sin == 0x200
        assert AfsDirectory.from_bytes(raw).find("readme").sin == 0x200

    def test_find_missing_raises(self) -> None:
        raw = build_directory_bytes("$", 0, [], 512)
        with pytest.raises(KeyError, match="no entry named"):
            AfsDirectory.from_bytes(raw).find("Nope")


# ---------------------------------------------------------------------------
# Many entries, alphabetical order
# ---------------------------------------------------------------------------


class TestMultipleEntries:
    def _build_random_order_directory(self) -> bytes:
        entries = [
            _file_entry("Zebra", 0x100),
            _file_entry("Alpha", 0x200),
            _file_entry("Mike", 0x300),
            _dir_entry("Charlie", 0x400),
            _dir_entry("Yankee", 0x500),
        ]
        return build_directory_bytes("$", 0, entries, 512)

    def test_in_use_list_is_alphabetical(self) -> None:
        parsed = AfsDirectory.from_bytes(self._build_random_order_directory())
        assert [e.name for e in parsed] == [
            "Alpha",
            "Charlie",
            "Mike",
            "Yankee",
            "Zebra",
        ]

    def test_num_entries(self) -> None:
        parsed = AfsDirectory.from_bytes(self._build_random_order_directory())
        assert len(parsed) == 5

    def test_contains(self) -> None:
        parsed = AfsDirectory.from_bytes(self._build_random_order_directory())
        assert parsed.contains("Alpha")
        assert parsed.contains("alpha")  # case-insensitive
        assert not parsed.contains("Bravo")

    def test_directory_vs_file_flag(self) -> None:
        parsed = AfsDirectory.from_bytes(self._build_random_order_directory())
        assert parsed.find("Charlie").is_directory
        assert parsed.find("Yankee").is_directory
        assert not parsed.find("Alpha").is_directory

    def test_locked_flag(self) -> None:
        parsed = AfsDirectory.from_bytes(self._build_random_order_directory())
        # Files built with "LR/R" are locked; directories with "DL/" are locked.
        for entry in parsed:
            assert entry.is_locked


# ---------------------------------------------------------------------------
# Slot layout — fills from the end
# ---------------------------------------------------------------------------


class TestSlotLayout:
    def test_single_entry_lands_in_last_slot(self) -> None:
        """The server fills a directory from the end; a one-entry directory
        should have its entry in slot 18 (the highest slot of a 19-slot
        directory)."""
        entry = _file_entry("HELLO", 0x100)
        raw = build_directory_bytes("$", 0, [entry], 512)
        parsed = AfsDirectory.from_bytes(raw)
        # The in-use list pointer should point to slot 18.
        first_pointer = int.from_bytes(raw[0:2], "little")
        slot_18_offset = HEADER_SIZE + 18 * ENTRY_SIZE  # = 17 + 468 = 485
        assert first_pointer == slot_18_offset
        # And parsing still recovers the single entry.
        assert len(parsed) == 1


# ---------------------------------------------------------------------------
# Capacity derivation
# ---------------------------------------------------------------------------


class TestCapacity:
    def test_default_two_sector_is_19(self) -> None:
        raw = build_directory_bytes("$", 0, [], 512)
        assert AfsDirectory.from_bytes(raw).capacity == 19

    def test_one_sector_is_9(self) -> None:
        raw = build_directory_bytes("$", 0, [], 256)
        assert AfsDirectory.from_bytes(raw).capacity == 9

    def test_three_sectors_is_28(self) -> None:
        # (768 - 18) / 26 = 28.8 → 28 slots.
        raw = build_directory_bytes("$", 0, [], 768)
        assert AfsDirectory.from_bytes(raw).capacity == 28

    def test_max_dir_capped_at_255(self) -> None:
        # 26 sectors = 6656 bytes → (6656 - 18) / 26 = 255.3 → capped at 255
        raw = build_directory_bytes("$", 0, [], 6656)
        assert AfsDirectory.from_bytes(raw).capacity == 255


# ---------------------------------------------------------------------------
# Master sequence number validation
# ---------------------------------------------------------------------------


class TestMasterSeqMismatch:
    def test_broken_directory_error(self) -> None:
        raw = bytearray(build_directory_bytes("$", 5, [], 512))
        raw[-1] = 99  # trailing copy disagrees with leading 5
        with pytest.raises(AFSBrokenDirectoryError, match="master-sequence"):
            AfsDirectory.from_bytes(bytes(raw))


# ---------------------------------------------------------------------------
# Parse errors
# ---------------------------------------------------------------------------


class TestParseErrors:
    def test_too_small(self) -> None:
        with pytest.raises(AFSBrokenDirectoryError, match="too small"):
            AfsDirectory.from_bytes(b"\x00" * (MIN_DIRECTORY_SIZE - 1))

    def test_bad_pointer_below_header(self) -> None:
        raw = bytearray(build_directory_bytes("$", 0, [], 512))
        # Point DRFRST at byte 5 (inside the header) and claim one entry.
        raw[0:2] = (5).to_bytes(2, "little")
        raw[15:17] = (1).to_bytes(2, "little")
        with pytest.raises(AFSBrokenDirectoryError, match="below header"):
            AfsDirectory.from_bytes(bytes(raw))

    def test_bad_pointer_unaligned(self) -> None:
        raw = bytearray(build_directory_bytes("$", 0, [], 512))
        # HEADER_SIZE + 1 = 18, which is not on a slot boundary (17 is).
        raw[0:2] = (18).to_bytes(2, "little")
        raw[15:17] = (1).to_bytes(2, "little")
        with pytest.raises(AFSBrokenDirectoryError, match="not on a slot boundary"):
            AfsDirectory.from_bytes(bytes(raw))

    def test_bad_pointer_out_of_range(self) -> None:
        raw = bytearray(build_directory_bytes("$", 0, [], 512))
        raw[0:2] = (HEADER_SIZE + 100 * ENTRY_SIZE).to_bytes(2, "little")
        raw[15:17] = (1).to_bytes(2, "little")
        with pytest.raises(AFSBrokenDirectoryError, match="outside capacity"):
            AfsDirectory.from_bytes(bytes(raw))

    def test_num_entries_disagreement(self) -> None:
        raw = bytearray(build_directory_bytes("$", 0, [_file_entry("A", 0x100)], 512))
        # Override DRENTS to claim 5 while there is only 1 in the list.
        raw[15:17] = (5).to_bytes(2, "little")
        with pytest.raises(AFSBrokenDirectoryError, match="disagrees with DRENTS"):
            AfsDirectory.from_bytes(bytes(raw))


# ---------------------------------------------------------------------------
# Builder error handling
# ---------------------------------------------------------------------------


class TestBuilderErrors:
    def test_too_many_entries_for_capacity(self) -> None:
        entries = [_file_entry(f"F{i}", 0x100 + i) for i in range(20)]
        with pytest.raises(ValueError, match="cannot fit"):
            build_directory_bytes("$", 0, entries, 512)

    def test_bad_size(self) -> None:
        with pytest.raises(ValueError, match="below minimum"):
            build_directory_bytes("$", 0, [], 10)

    def test_non_multiple_of_sector(self) -> None:
        with pytest.raises(ValueError, match="multiple of 256"):
            build_directory_bytes("$", 0, [], 500)


# ---------------------------------------------------------------------------
# DirectoryEntry validation
# ---------------------------------------------------------------------------


class TestDirectoryEntryValidation:
    def test_empty_name(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            DirectoryEntry(
                name="",
                load_address=0,
                exec_address=0,
                access=AFSAccess.from_string("/"),
                date=_sample_date(),
                sin=SystemInternalName(0x100),
            )

    def test_name_too_long(self) -> None:
        with pytest.raises(ValueError, match="exceeds 10"):
            DirectoryEntry(
                name="A" * 11,
                load_address=0,
                exec_address=0,
                access=AFSAccess.from_string("/"),
                date=_sample_date(),
                sin=SystemInternalName(0x100),
            )


class TestMaxEntries:
    def test_max_entries_constant(self) -> None:
        assert MAX_ENTRIES == 255

    def test_max_name_length_constant(self) -> None:
        assert MAX_NAME_LENGTH == 10

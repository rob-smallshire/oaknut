"""Tests for ADFS old-format directory serialization.

Round-trip tests: build directory bytes with the test helper, parse them,
serialize them back, and verify the result matches the original bytes
or parses identically.
"""

import pytest

from helpers.adfs_image import (
    make_old_dir_entry as _make_old_dir_entry,
    make_old_directory as _make_old_directory,
)
from oaknut_dfs.adfs_directory import (
    OldDirectoryFormat,
    _ADFSDirectory,
    _ADFSDirectoryEntry,
    _ADFSRawAttributes,
)
from oaknut_dfs.sectors_view import SectorsView


class TestOldDirectorySerializeRoundTrip:
    """Parse directory bytes, serialize back, verify identical bytes."""

    def _round_trip(self, original_bytes: bytearray) -> bytearray:
        """Parse then serialize, returning the serialized bytes."""
        fmt = OldDirectoryFormat()
        view = SectorsView([memoryview(original_bytes)])
        directory = fmt.parse(view, disc_address=2)

        output = bytearray(1280)
        out_view = SectorsView([memoryview(output)])
        fmt.serialize(directory, out_view)
        return output

    def test_empty_directory(self):
        original = _make_old_directory([], dir_name="$", title="TestDisc")
        result = self._round_trip(original)
        assert result == original

    def test_single_file(self):
        entries = [
            _make_old_dir_entry("Hello", load_address=0x1900,
                                exec_address=0x8023, length=256,
                                indirect_disc_address=7),
        ]
        original = _make_old_directory(entries, title="MyDisc")
        result = self._round_trip(original)
        assert result == original

    def test_multiple_files(self):
        entries = [
            _make_old_dir_entry("Alpha", load_address=0x1900, length=100,
                                indirect_disc_address=7),
            _make_old_dir_entry("Beta", load_address=0x2000, length=512,
                                indirect_disc_address=8),
            _make_old_dir_entry("Gamma", load_address=0x3000, length=1024,
                                indirect_disc_address=10),
        ]
        original = _make_old_directory(entries, title="ThreeFiles")
        result = self._round_trip(original)
        assert result == original

    def test_directory_entry(self):
        entries = [
            _make_old_dir_entry("Games", length=1280,
                                indirect_disc_address=32,
                                is_directory=True),
        ]
        original = _make_old_directory(entries)
        result = self._round_trip(original)
        assert result == original

    def test_locked_file(self):
        entries = [
            _make_old_dir_entry("Secret", locked=True,
                                owner_read=True, owner_write=False,
                                length=64, indirect_disc_address=7),
        ]
        original = _make_old_directory(entries)
        result = self._round_trip(original)
        assert result == original

    def test_custom_parent_address(self):
        original = _make_old_directory([], parent_address=0x200)
        result = self._round_trip(original)
        assert result == original

    def test_sequence_number_preserved(self):
        original = _make_old_directory([], sequence_number=42)
        result = self._round_trip(original)
        assert result == original

    def test_nick_signature_normalised_to_hugo(self):
        """Directories with 'Nick' signature are re-serialized as 'Hugo'."""
        original = _make_old_directory([], signature=b"Nick")
        result = self._round_trip(original)
        # Nick is accepted on read but Hugo is always written
        expected = _make_old_directory([], signature=b"Hugo")
        assert result == expected

    def test_subdirectory_name(self):
        original = _make_old_directory(
            [], dir_name="Games", title="Game Dir", parent_address=2,
        )
        result = self._round_trip(original)
        assert result == original

    def test_max_entries(self):
        entries = [
            _make_old_dir_entry(f"F{i:02d}", length=10,
                                indirect_disc_address=7 + i)
            for i in range(47)
        ]
        original = _make_old_directory(entries)
        result = self._round_trip(original)
        assert result == original

    def test_large_addresses(self):
        entries = [
            _make_old_dir_entry("Big",
                                load_address=0xFFFF1900,
                                exec_address=0xFFFF8023,
                                length=0x10000,
                                indirect_disc_address=0xABCDEF),
        ]
        original = _make_old_directory(entries)
        result = self._round_trip(original)
        assert result == original


class TestOldDirectorySerializeToSectorsView:
    """Test that serialize writes correctly into a SectorsView."""

    def test_serialize_writes_to_provided_view(self):
        """Serialize should write into the given SectorsView, not return bytes."""
        fmt = OldDirectoryFormat()
        entries = [
            _make_old_dir_entry("Test", load_address=0x1000, length=100,
                                indirect_disc_address=7),
        ]
        original = _make_old_directory(entries, title="ViewTest")
        view = SectorsView([memoryview(original)])
        directory = fmt.parse(view, disc_address=2)

        # Serialize into a fresh buffer
        output = bytearray(1280)
        out_view = SectorsView([memoryview(output)])
        fmt.serialize(directory, out_view)

        # Parse back and verify
        result_dir = fmt.parse(out_view, disc_address=2)
        assert result_dir.name == "$"
        assert result_dir.title == "ViewTest"
        assert len(result_dir.entries) == 1
        assert result_dir.entries[0].name == "Test"


class TestOldDirectorySerializeFromConstructed:
    """Test serializing _ADFSDirectory objects built programmatically."""

    def test_serialize_constructed_directory(self):
        """Build an _ADFSDirectory from scratch and serialize it."""
        fmt = OldDirectoryFormat()

        entry = _ADFSDirectoryEntry(
            name="NewFile",
            load_address=0x1900,
            exec_address=0x8023,
            length=256,
            indirect_disc_address=7,
            sequence_number=0,
            attributes=_ADFSRawAttributes(
                owner_read=True,
                owner_write=True,
                locked=False,
                directory=False,
                owner_execute=False,
                public_read=True,
                public_write=False,
                public_execute=False,
                private=False,
            ),
        )

        directory = _ADFSDirectory(
            name="$",
            title="Built",
            parent_address=2,
            disc_address=2,
            entries=(entry,),
            sequence_number=0,
        )

        output = bytearray(1280)
        out_view = SectorsView([memoryview(output)])
        fmt.serialize(directory, out_view)

        # Parse back and verify
        parsed = fmt.parse(out_view, disc_address=2)
        assert parsed.name == "$"
        assert parsed.title == "Built"
        assert len(parsed.entries) == 1
        assert parsed.entries[0].name == "NewFile"
        assert parsed.entries[0].load_address == 0x1900
        assert parsed.entries[0].exec_address == 0x8023
        assert parsed.entries[0].length == 256
        assert parsed.entries[0].indirect_disc_address == 7
        assert parsed.entries[0].attributes.owner_read is True
        assert parsed.entries[0].attributes.owner_write is True
        assert parsed.entries[0].attributes.locked is False
        assert parsed.entries[0].attributes.public_read is True

    def test_serialize_empty_constructed_directory(self):
        """An empty directory should serialize and parse back."""
        fmt = OldDirectoryFormat()

        directory = _ADFSDirectory(
            name="$",
            title="",
            parent_address=2,
            disc_address=2,
            entries=(),
            sequence_number=0,
        )

        output = bytearray(1280)
        out_view = SectorsView([memoryview(output)])
        fmt.serialize(directory, out_view)

        parsed = fmt.parse(out_view, disc_address=2)
        assert parsed.name == "$"
        assert parsed.title == ""
        assert parsed.entries == ()

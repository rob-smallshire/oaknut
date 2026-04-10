"""Tests for ADFS write operations.

Tests for writing files to ADFS disc images via ADFSPath.write_bytes()
and write_text().
"""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S, ADFS_M, ADFS_L
from oaknut_dfs.exceptions import (
    ADFSDiscFullError,
    ADFSDirectoryFullError,
    ADFSPathError,
)

# Ensure acorn codec is registered
import oaknut_dfs.acorn_encoding  # noqa: F401


class TestWriteBytes:

    def test_write_and_read_back(self):
        adfs = ADFS.create(ADFS_S)
        data = b"Hello, ADFS!"
        (adfs.root / "Hello").write_bytes(data, load_address=0x1900)
        assert (adfs.root / "Hello").read_bytes() == data

    def test_write_sets_metadata(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Test").write_bytes(
            b"data",
            load_address=0x1900,
            exec_address=0x8023,
        )
        stat = (adfs.root / "Test").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023
        assert stat.length == 4

    def test_write_locked_file(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Secret").write_bytes(b"hidden", locked=True)
        stat = (adfs.root / "Secret").stat()
        assert stat.locked is True

    def test_write_empty_file(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Empty").write_bytes(b"")
        assert (adfs.root / "Empty").read_bytes() == b""
        assert (adfs.root / "Empty").stat().length == 0

    def test_write_exact_sector_boundary(self):
        adfs = ADFS.create(ADFS_S)
        data = b"\xAA" * 256
        (adfs.root / "OneSec").write_bytes(data)
        assert (adfs.root / "OneSec").read_bytes() == data

    def test_write_spanning_sectors(self):
        adfs = ADFS.create(ADFS_S)
        data = b"\xBB" * 300  # Spans 2 sectors
        (adfs.root / "TwoSec").write_bytes(data)
        assert (adfs.root / "TwoSec").read_bytes() == data

    def test_write_large_file(self):
        adfs = ADFS.create(ADFS_M)
        data = bytes(range(256)) * 40  # 10240 bytes = 40 sectors
        (adfs.root / "Big").write_bytes(data)
        assert (adfs.root / "Big").read_bytes() == data

    def test_write_multiple_files(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "First").write_bytes(b"one")
        (adfs.root / "Second").write_bytes(b"two")
        (adfs.root / "Third").write_bytes(b"three")

        assert (adfs.root / "First").read_bytes() == b"one"
        assert (adfs.root / "Second").read_bytes() == b"two"
        assert (adfs.root / "Third").read_bytes() == b"three"
        assert len(list(adfs.root)) == 3

    def test_write_updates_free_space(self):
        adfs = ADFS.create(ADFS_S)
        initial_free = adfs.free_space
        (adfs.root / "File").write_bytes(b"\x00" * 512)  # 2 sectors
        assert adfs.free_space == initial_free - 512

    def test_file_appears_in_directory(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Hello").write_bytes(b"data")
        names = [p.name for p in adfs.root]
        assert "Hello" in names

    def test_file_exists_after_write(self):
        adfs = ADFS.create(ADFS_S)
        path = adfs.root / "Hello"
        assert not path.exists()
        path.write_bytes(b"data")
        assert path.exists()
        assert path.is_file()

    def test_write_to_root_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError):
            adfs.root.write_bytes(b"data")

    def test_disc_full_raises(self):
        adfs = ADFS.create(ADFS_S)
        # ADFS S has 633 free sectors (640 - 7 used)
        # Try to write more than that
        with pytest.raises(ADFSDiscFullError):
            (adfs.root / "Huge").write_bytes(b"\x00" * (634 * 256))

    def test_overwrite_existing_file(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"original")
        (adfs.root / "File").write_bytes(b"replaced")
        assert (adfs.root / "File").read_bytes() == b"replaced"
        # Should still be one file, not two
        assert len(list(adfs.root)) == 1

    def test_overwrite_frees_old_sectors(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"\x00" * 2560)  # 10 sectors
        free_after_first = adfs.free_space
        (adfs.root / "File").write_bytes(b"\x00" * 256)   # 1 sector
        # Should have freed 9 sectors
        assert adfs.free_space == free_after_first + 9 * 256

    def test_validate_after_write(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"test data")
        assert adfs.validate() == []


class TestWriteText:

    def test_write_text_default_acorn_encoding(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Text").write_text("Hello")
        assert (adfs.root / "Text").read_bytes() == b"Hello"

    def test_write_text_pound_sign(self):
        """The pound sign is 0x60 in Acorn encoding, not 0xC2 0xA3 (UTF-8)."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Price").write_text("\u00a3")  # £
        data = (adfs.root / "Price").read_bytes()
        assert data == b"\x60"

    def test_write_text_with_metadata(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Doc").write_text("Notes", load_address=0xFFFF1900)
        stat = (adfs.root / "Doc").stat()
        assert stat.load_address == 0xFFFF1900

    def test_write_text_explicit_encoding(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Utf").write_text("Hello", encoding="utf-8")
        assert (adfs.root / "Utf").read_bytes() == b"Hello"


class TestReadText:

    def test_read_text_default_acorn_encoding(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Text").write_text("Hello")
        assert (adfs.root / "Text").read_text() == "Hello"

    def test_read_text_pound_sign(self):
        """The pound sign round-trips via Acorn encoding (0x60)."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Price").write_text("\u00a3")  # £
        assert (adfs.root / "Price").read_text() == "\u00a3"

    def test_read_text_explicit_encoding(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Utf").write_bytes("Héllo".encode("utf-8"))
        assert (adfs.root / "Utf").read_text(encoding="utf-8") == "Héllo"

    def test_read_text_round_trip_utf8(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Utf").write_text("Héllo", encoding="utf-8")
        assert (adfs.root / "Utf").read_text(encoding="utf-8") == "Héllo"


class TestDirectoryFull:

    def test_directory_full_raises(self):
        adfs = ADFS.create(ADFS_M)
        # Old-format directories hold 47 entries max
        for i in range(47):
            (adfs.root / f"F{i:02d}").write_bytes(b"x")

        with pytest.raises(ADFSDirectoryFullError):
            (adfs.root / "OneMore").write_bytes(b"x")

    def test_directory_full_after_47_files(self):
        adfs = ADFS.create(ADFS_M)
        for i in range(47):
            (adfs.root / f"F{i:02d}").write_bytes(b"x")

        assert len(list(adfs.root)) == 47


class TestWriteRoundTripWithBuffer:

    def test_write_then_reopen(self):
        """Write a file, reopen the buffer, and read it back."""
        adfs = ADFS.create(ADFS_S, title="WriteTest")
        (adfs.root / "Greet").write_bytes(
            b"Hello!", load_address=0x1900, exec_address=0x8023
        )

        # Reopen from the same buffer
        buffer = adfs._disc._disc_image.buffer
        adfs2 = ADFS.from_buffer(buffer)
        assert (adfs2.root / "Greet").read_bytes() == b"Hello!"
        stat = (adfs2.root / "Greet").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023
        assert stat.length == 6

    def test_write_multiple_then_reopen(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "A").write_bytes(b"aaa")
        (adfs.root / "B").write_bytes(b"bbb")
        (adfs.root / "C").write_bytes(b"ccc")

        buffer = adfs._disc._disc_image.buffer
        adfs2 = ADFS.from_buffer(buffer)
        assert (adfs2.root / "A").read_bytes() == b"aaa"
        assert (adfs2.root / "B").read_bytes() == b"bbb"
        assert (adfs2.root / "C").read_bytes() == b"ccc"

"""Tests for ADFS.compact() — free space defragmentation."""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S, ADFS_M


class TestCompactBasic:

    def test_compact_empty_disc(self):
        adfs = ADFS.create(ADFS_S)
        adfs.compact()
        assert adfs.validate() == []

    def test_compact_returns_num_objects(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "A").write_bytes(b"aaa")
        (adfs.root / "B").write_bytes(b"bbb")
        result = adfs.compact()
        assert result == 2

    def test_compact_preserves_file_data(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Alpha").write_bytes(b"alpha data")
        (adfs.root / "Beta").write_bytes(b"beta data")
        adfs.compact()
        assert (adfs.root / "Alpha").read_bytes() == b"alpha data"
        assert (adfs.root / "Beta").read_bytes() == b"beta data"

    def test_compact_preserves_metadata(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Prog").write_bytes(
            b"code", load_address=0x1900, exec_address=0x8023, locked=True,
        )
        adfs.compact()
        stat = (adfs.root / "Prog").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023
        assert stat.locked is True

    def test_compact_preserves_title(self):
        adfs = ADFS.create(ADFS_S, title="MyDisc")
        (adfs.root / "File").write_bytes(b"data")
        adfs.compact()
        assert adfs.title == "MyDisc"

    def test_compact_preserves_boot_option(self):
        adfs = ADFS.create(ADFS_S, boot_option=3)
        (adfs.root / "File").write_bytes(b"data")
        adfs.compact()
        assert adfs.boot_option == 3

    def test_compact_validates_clean(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        adfs.compact()
        assert adfs.validate() == []


class TestCompactDefragmentation:

    def test_compact_consolidates_free_space(self):
        adfs = ADFS.create(ADFS_S)
        # Create files, delete middle one to create fragmentation
        (adfs.root / "A").write_bytes(b"\x00" * 256)
        (adfs.root / "B").write_bytes(b"\x00" * 256)
        (adfs.root / "C").write_bytes(b"\x00" * 256)
        (adfs.root / "B").unlink()

        # Free space is now fragmented (gap where B was)
        free_before = adfs.free_space
        fsm_entries_before = len(adfs._fsm.free_space_entries())

        adfs.compact()

        # Free space total should be the same
        assert adfs.free_space == free_before
        # But consolidated into fewer entries (ideally one)
        fsm_entries_after = len(adfs._fsm.free_space_entries())
        assert fsm_entries_after <= fsm_entries_before
        assert adfs.validate() == []

    def test_compact_after_multiple_deletes(self):
        adfs = ADFS.create(ADFS_M)
        # Create many files
        for i in range(10):
            (adfs.root / f"F{i:02d}").write_bytes(b"\x00" * 512)

        # Delete alternating files to maximise fragmentation
        for i in range(0, 10, 2):
            (adfs.root / f"F{i:02d}").unlink()

        free_before = adfs.free_space
        adfs.compact()

        # All remaining files still readable
        for i in range(1, 10, 2):
            assert (adfs.root / f"F{i:02d}").read_bytes() == b"\x00" * 512

        assert adfs.free_space == free_before
        assert adfs.validate() == []

    def test_compact_single_free_entry_after(self):
        """After compaction, the free space map should have exactly one entry."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "A").write_bytes(b"\x00" * 256)
        (adfs.root / "B").write_bytes(b"\x00" * 256)
        (adfs.root / "C").write_bytes(b"\x00" * 256)
        (adfs.root / "A").unlink()
        (adfs.root / "C").unlink()

        adfs.compact()
        assert len(adfs._fsm.free_space_entries()) == 1


class TestCompactWithDirectories:

    def test_compact_preserves_subdirectories(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games" / "Elite").write_bytes(b"game data")
        (adfs.root / "Docs").mkdir()
        (adfs.root / "Docs" / "Readme").write_bytes(b"read me")

        adfs.compact()

        assert (adfs.root / "Games").is_dir()
        assert (adfs.root / "Games" / "Elite").read_bytes() == b"game data"
        assert (adfs.root / "Docs").is_dir()
        assert (adfs.root / "Docs" / "Readme").read_bytes() == b"read me"

    def test_compact_preserves_directory_titles(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games").title = "Game Collection"

        adfs.compact()
        assert (adfs.root / "Games").title == "Game Collection"

    def test_compact_with_nested_dirs_and_fragmentation(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir" / "Keep").write_bytes(b"keep")
        (adfs.root / "Temp").write_bytes(b"\x00" * 1024)
        (adfs.root / "Temp").unlink()

        adfs.compact()

        assert (adfs.root / "Dir" / "Keep").read_bytes() == b"keep"
        assert not (adfs.root / "Temp").exists()
        assert adfs.validate() == []


class TestCompactRoundTrip:

    def test_compact_then_reopen(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"hello", load_address=0x1900)
        (adfs.root / "Temp").write_bytes(b"\x00" * 512)
        (adfs.root / "Temp").unlink()

        adfs.compact()

        buffer = adfs._disc._disc_image.buffer
        adfs2 = ADFS.from_buffer(buffer)
        assert (adfs2.root / "File").read_bytes() == b"hello"
        assert (adfs2.root / "File").stat().load_address == 0x1900
        assert adfs2.validate() == []

    def test_compact_then_write_more(self):
        """After compaction, should be able to write new files."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Old").write_bytes(b"\x00" * 256)
        (adfs.root / "Del").write_bytes(b"\x00" * 256)
        (adfs.root / "Del").unlink()

        adfs.compact()

        (adfs.root / "New").write_bytes(b"new data")
        assert (adfs.root / "New").read_bytes() == b"new data"
        assert adfs.validate() == []

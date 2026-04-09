"""Tests for advanced DFS operations (free space, validation, compaction)."""

import pytest

from oaknut_dfs.dfs import DFS
from oaknut_dfs.formats import (
    ACORN_DFS_40T_SINGLE_SIDED,
)


class TestFreeSpace:
    """Tests for free_sectors, get_free_map(), and info property."""

    def test_free_sectors_empty_disk(self):
        """Test free_sectors on empty disk."""
        buffer = bytearray(102400)

        # Empty catalog
        buffer[0:8] = b"EMPTY   "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # 400 total sectors - 2 catalog sectors = 398 free
        assert dfs.free_sectors == 398

    def test_free_sectors_with_files(self):
        """Test free_sectors with files taking up space."""
        buffer = bytearray(102400)

        # Empty catalog
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Add a 100-byte file (takes 1 sector)
        (dfs.root / "$" / "FILE1").write_bytes(b"X" * 100)
        assert dfs.free_sectors == 397  # 398 - 1

        # Add a 300-byte file (takes 2 sectors)
        (dfs.root / "$" / "FILE2").write_bytes(b"Y" * 300)
        assert dfs.free_sectors == 395  # 397 - 2

    def test_get_free_map_empty_disk(self):
        """Test get_free_map on empty disk."""
        buffer = bytearray(102400)

        buffer[0:8] = b"EMPTY   "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        free_map = dfs._catalogued_surface.get_free_map()

        # Should be one contiguous region from sector 2 to end
        assert len(free_map) == 1
        assert free_map[0] == (2, 398)  # Start at sector 2, length 398

    def test_get_free_map_with_gaps(self):
        """Test get_free_map with fragmented free space."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Add files to create gaps
        (dfs.root / "$" / "FILE1").write_bytes(b"X" * 256)  # 1 sector at sector 2
        (dfs.root / "$" / "FILE2").write_bytes(b"Y" * 256)  # 1 sector at sector 3

        # Delete first file to create gap
        (dfs.root / "$" / "FILE1").unlink()

        free_map = dfs._catalogued_surface.get_free_map()

        # Should have a gap at sector 2, then free space from sector 4 onward
        assert len(free_map) == 2
        assert free_map[0] == (2, 1)  # Gap at sector 2
        assert free_map[1][0] == 4  # Free space starts at sector 4

    def test_info_property(self):
        """Test info property returns complete disk information."""
        buffer = bytearray(102400)

        buffer[0:8] = b"TESTINFO"
        buffer[256:260] = b"    "
        buffer[260] = 5  # Cycle number
        buffer[261] = 0
        buffer[262] = 0x20  # Boot option 2
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        info = dfs.info

        assert info["title"] == "TESTINFO"
        assert info["num_files"] == 0
        assert info["total_sectors"] == 200
        assert info["free_sectors"] == 398  # 400 - 2 catalog
        assert info["boot_option"] == 2


class TestFileInfo:
    """Tests for get_file_info()."""

    def test_get_file_info(self):
        """Test getting detailed file information."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Save a file
        (dfs.root / "$" / "HELLO").write_bytes(b"Test content", load_address=0x1900, exec_address=0x8023)

        # Get file info
        st = (dfs.root / "$" / "HELLO").stat()

        assert not st.locked
        assert st.load_address == 0x1900
        assert st.exec_address == 0x8023
        assert st.length == 12
        assert st.start_sector == 2

    def test_get_file_info_not_found(self):
        """Test get_file_info for nonexistent file."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        with pytest.raises(FileNotFoundError):
            (dfs.root / "$" / "NOSUCHFILE").stat()


class TestValidation:
    """Tests for validate()."""

    def test_validate_clean_disk(self):
        """Test validate on clean disk returns no errors."""
        buffer = bytearray(102400)

        buffer[0:8] = b"CLEAN   "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Add some files
        (dfs.root / "$" / "FILE1").write_bytes(b"data1")
        (dfs.root / "$" / "FILE2").write_bytes(b"data2")

        errors = dfs.validate()
        assert errors == []

    def test_validate_duplicate_names(self):
        """Test validate detects duplicate filenames."""
        buffer = bytearray(102400)

        # Manually create catalog with duplicate names
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 16  # 2 files
        buffer[262] = 0x00
        buffer[263] = 200

        # File 1: $.TEST at sector 2
        buffer[8:15] = b"TEST   "
        buffer[15] = ord("$")
        buffer[256 + 8:256 + 16] = bytes([0, 0, 0, 0, 100, 0, 0, 2])

        # File 2: $.TEST at sector 4 (duplicate!)
        buffer[16:23] = b"TEST   "
        buffer[23] = ord("$")
        buffer[256 + 16:256 + 24] = bytes([0, 0, 0, 0, 100, 0, 0, 4])

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        errors = dfs.validate()
        assert len(errors) == 1
        assert "Duplicate" in errors[0]
        assert "$.TEST" in errors[0]


class TestCompaction:
    """Tests for compact()."""

    def test_compact_fragmented_disk(self):
        """Test compacting a fragmented disk."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Create fragmentation
        (dfs.root / "$" / "FILE1").write_bytes(b"A" * 256)  # Sector 2
        (dfs.root / "$" / "FILE2").write_bytes(b"B" * 256)  # Sector 3
        (dfs.root / "$" / "FILE3").write_bytes(b"C" * 256)  # Sector 4

        # Delete middle file
        (dfs.root / "$" / "FILE2").unlink()

        # Now we have: FILE1 at 2, gap at 3, FILE3 at 4

        # Compact
        moved = dfs.compact()

        # Should move FILE3 to fill the gap
        assert moved == 2  # Both files rewritten

        # Verify files are sequential now
        files = dfs.files
        assert files[0].start_sector == 2
        assert files[1].start_sector == 3  # No more gap

        # Verify data is intact
        assert (dfs.root / "$" / "FILE1").read_bytes() == b"A" * 256
        assert (dfs.root / "$" / "FILE3").read_bytes() == b"C" * 256

    def test_compact_with_locked_files_raises(self):
        """Test compact raises error if locked files present."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Add a locked file
        (dfs.root / "$" / "LOCKED").write_bytes(b"data", locked=True)

        with pytest.raises(PermissionError, match="locked files present"):
            dfs.compact()

    def test_compact_already_compact(self):
        """Test compact on already compact disk."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Add files sequentially
        (dfs.root / "$" / "FILE1").write_bytes(b"A" * 100)
        (dfs.root / "$" / "FILE2").write_bytes(b"B" * 100)

        # Already compact
        moved = dfs.compact()
        assert moved == 2  # All files rewritten

    def test_compact_empty_disk(self):
        """Test compact on empty disk."""
        buffer = bytearray(102400)

        buffer[0:8] = b"EMPTY   "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        moved = dfs.compact()
        assert moved == 0

    def test_compact_preserves_metadata(self):
        """Test compact preserves file metadata."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Add file with specific metadata
        (dfs.root / "$" / "PROG").write_bytes(b"X" * 500, load_address=0x1900, exec_address=0x8023)

        # Add another file then delete it to create fragmentation
        (dfs.root / "$" / "TEMP").write_bytes(b"Y" * 100)
        (dfs.root / "$" / "TEMP").unlink()

        # Compact
        dfs.compact()

        # Verify metadata preserved
        st = (dfs.root / "$" / "PROG").stat()
        assert st.load_address == 0x1900
        assert st.exec_address == 0x8023
        assert st.length == 500

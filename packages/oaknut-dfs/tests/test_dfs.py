"""Tests for DFS high-level class."""

import shutil

import pytest
import oaknut_dfs.acorn_encoding  # Register codec

from oaknut_dfs.dfs import DFS
from oaknut_dfs.formats import (
    ACORN_DFS_40T_SINGLE_SIDED,
    ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_80T_SINGLE_SIDED,
)

GAME_IMAGE_FILEPATH = (
    pytest.importorskip("pathlib").Path(__file__).parent
    / "data" / "images" / "games" / "Disc003-Zalaga.ssd"
)


class TestDFSNamedConstructors:
    """Tests for from_ssd() and from_dsd()."""

    def test_from_ssd_creates_dfs(self):
        """Test creating DFS from SSD buffer."""
        # Create minimal SSD image (40 tracks * 10 sectors * 256 bytes)
        buffer = bytearray(102400)

        # Initialize catalog
        buffer[0:8] = b"TESTSSD "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        assert dfs.title == "TESTSSD"
        assert dfs.boot_option == 0
        assert len(dfs.files) == 0

    def test_from_dsd_creates_dfs_side0(self):
        """Test creating DFS from DSD buffer side 0."""
        # Create minimal DSD image (80 tracks * 10 sectors * 256 bytes)
        buffer = bytearray(204800)

        # Initialize catalog for side 0 (tracks 0, 2, 4, ...)
        buffer[0:8] = b"DSD0    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=0)

        assert dfs.title == "DSD0"

    def test_from_dsd_creates_dfs_side1(self):
        """Test creating DFS from DSD buffer side 1."""
        buffer = bytearray(204800)

        # Initialize catalog for side 1 (tracks 1, 3, 5, ...)
        # Side 1 starts at offset 2560 (one track)
        buffer[2560:2568] = b"DSD1    "
        buffer[2560 + 256:2560 + 260] = b"    "
        buffer[2560 + 260] = 0
        buffer[2560 + 261] = 0
        buffer[2560 + 262] = 0x00
        buffer[2560 + 263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=1)

        assert dfs.title == "DSD1"

    def test_from_dsd_invalid_side(self):
        """Test that invalid side raises error."""
        buffer = bytearray(204800)

        with pytest.raises(IndexError, match="side must be in range"):
            DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=2)


class TestDFSFileOperations:
    """Tests for load(), save(), delete()."""

    def test_save_and_load_file(self):
        """Test saving and loading a file."""
        buffer = bytearray(102400)

        # Empty catalog
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Save a file
        file_data = b"Hello, World!"
        dfs.save("$.HELLO", file_data, load_address=0x1000, exec_address=0x2000)

        # Load it back
        loaded = dfs.load("$.HELLO")
        assert loaded == file_data

        # Verify it's in the file list
        assert len(dfs.files) == 1
        assert dfs.files[0].filename == "HELLO"
        assert dfs.files[0].load_address == 0x1000
        assert dfs.files[0].exec_address == 0x2000

    def test_save_without_directory_prefix(self):
        """Test saving file without directory prefix defaults to $."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.save("TEST", b"data")

        assert len(dfs.files) == 1
        assert dfs.files[0].directory == "$"
        assert dfs.files[0].filename == "TEST"

    def test_delete_file(self):
        """Test deleting a file."""
        buffer = bytearray(102400)

        # Catalog with 1 file
        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8
        buffer[262] = 0x00
        buffer[263] = 200

        buffer[8:15] = b"TODEL  "  # Max 7 chars
        buffer[15] = ord("$")
        buffer[256 + 8:256 + 16] = bytes([0, 0, 0, 0, 100, 0, 0, 2])

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        assert len(dfs.files) == 1

        dfs.delete("$.TODEL")

        assert len(dfs.files) == 0

    def test_exists(self):
        """Test exists() method."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8
        buffer[262] = 0x00
        buffer[263] = 200

        buffer[8:15] = b"EXISTS "
        buffer[15] = ord("$")
        buffer[256 + 8:256 + 16] = bytes([0, 0, 0, 0, 100, 0, 0, 2])

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        assert dfs.exists("$.EXISTS") == True
        assert dfs.exists("$.NOSUCHFILE") == False


class TestDFSRenameAndLock:
    """Tests for rename(), lock(), unlock()."""

    def test_rename_file(self):
        """Test renaming a file."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8
        buffer[262] = 0x00
        buffer[263] = 200

        buffer[8:15] = b"OLDNAME"
        buffer[15] = ord("$")
        buffer[256 + 8:256 + 16] = bytes([0, 0, 0, 0, 100, 0, 0, 2])

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.rename("$.OLDNAME", "$.NEWNAME")

        assert len(dfs.files) == 1
        assert dfs.files[0].filename == "NEWNAME"

    def test_lock_and_unlock(self):
        """Test locking and unlocking a file."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 8
        buffer[262] = 0x00
        buffer[263] = 200

        buffer[8:15] = b"TEST   "
        buffer[15] = ord("$")
        buffer[256 + 8:256 + 16] = bytes([0, 0, 0, 0, 100, 0, 0, 2])

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Initially unlocked
        assert dfs.files[0].locked == False

        # Lock it
        dfs.lock("$.TEST")
        assert dfs.files[0].locked == True

        # Unlock it
        dfs.unlock("$.TEST")
        assert dfs.files[0].locked == False


class TestDFSMetadata:
    """Tests for title and boot_option properties."""

    def test_get_title(self):
        """Test getting disk title."""
        buffer = bytearray(102400)

        buffer[0:8] = b"MYTITLE "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        assert dfs.title == "MYTITLE"

    def test_set_title(self):
        """Test setting disk title."""
        buffer = bytearray(102400)

        buffer[0:8] = b"OLD     "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.title = "NEWTITLE"

        assert dfs.title == "NEWTITLE"

    def test_get_boot_option(self):
        """Test getting boot option."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x20  # Boot option 2
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        assert dfs.boot_option == 2

    def test_set_boot_option(self):
        """Test setting boot option."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.boot_option = 3

        assert dfs.boot_option == 3


class TestDFSCopyFile:
    """Tests for copy_file()."""

    def test_copy_file_preserves_data_and_metadata(self):
        """Test copying file preserves all data and metadata."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Save file with specific metadata
        original_data = b"Test file contents"
        dfs.save("$.ORIG", original_data, load_address=0x1900, exec_address=0x8023)

        # Copy it
        dfs.copy_file("$.ORIG", "$.COPY")

        # Both files should exist
        assert dfs.exists("$.ORIG")
        assert dfs.exists("$.COPY")

        # Copy should have same data
        assert dfs.load("$.COPY") == original_data

        # Copy should have same metadata
        original_info = dfs.get_file_info("$.ORIG")
        copy_info = dfs.get_file_info("$.COPY")

        assert copy_info.load_address == original_info.load_address
        assert copy_info.exec_address == original_info.exec_address
        assert copy_info.length == original_info.length

    def test_copy_file_to_different_directory(self):
        """Test copying file to different directory."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.save("$.FILE", b"data")
        dfs.copy_file("$.FILE", "A.FILE")

        assert dfs.exists("$.FILE")
        assert dfs.exists("A.FILE")

        # Check directory
        files = dfs.files
        assert any(f.directory == "$" and f.filename == "FILE" for f in files)
        assert any(f.directory == "A" and f.filename == "FILE" for f in files)

    def test_copy_file_preserves_locked_status(self):
        """Test copying locked file preserves locked status."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Save and lock file
        dfs.save("$.LOCKED", b"data", locked=True)

        # Copy it
        dfs.copy_file("$.LOCKED", "$.COPY2")

        # Both should be locked
        assert dfs.get_file_info("$.LOCKED").locked == True
        assert dfs.get_file_info("$.COPY2").locked == True

    def test_copy_file_nonexistent_raises(self):
        """Test copying nonexistent file raises error."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        with pytest.raises(FileNotFoundError):
            dfs.copy_file("$.NOSUCHFILE", "$.COPY")


class TestDFSConvenienceMethods:
    """Tests for convenience methods (save_text, save_from_file)."""

    def test_save_text_utf8(self):
        """Test saving text with default UTF-8 encoding."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        text = "Hello, World!"
        dfs.save_text("$.TEXT", text)

        # Load and decode
        loaded = dfs.load("$.TEXT")
        assert loaded.decode("utf-8") == text

    def test_save_text_with_encoding(self):
        """Test saving text with specific encoding."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        text = "ASCII text"
        dfs.save_text("$.ASCII", text, encoding="ascii")

        loaded = dfs.load("$.ASCII")
        assert loaded.decode("ascii") == text

    def test_save_text_with_metadata(self):
        """Test save_text passes through metadata kwargs."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.save_text("$.PROG", "PRINT", load_address=0x1900, exec_address=0x8023)

        info = dfs.get_file_info("$.PROG")
        assert info.load_address == 0x1900
        assert info.exec_address == 0x8023

    def test_save_from_file(self, tmp_path):
        """Test saving from host filesystem."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Create source file
        source_file = tmp_path / "source.bin"
        source_data = b"Binary data from file"
        source_file.write_bytes(source_data)

        # Save from file
        dfs.save_from_file("$.COPY", str(source_file))

        # Verify
        assert dfs.load("$.COPY") == source_data

    def test_save_from_file_with_metadata(self, tmp_path):
        """Test save_from_file passes through metadata kwargs."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Create source file
        source_file = tmp_path / "program.bin"
        source_file.write_bytes(b"CODE")

        # Save with metadata
        dfs.save_from_file("$.PROG", str(source_file), load_address=0x1900, locked=True)

        # Verify
        info = dfs.get_file_info("$.PROG")
        assert info.load_address == 0x1900
        assert info.locked == True

    def test_save_from_file_nonexistent_raises(self):
        """Test save_from_file raises error for nonexistent source."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        with pytest.raises(FileNotFoundError):
            dfs.save_from_file("$.TEST", "/nonexistent/file.bin")


class TestDFSDirectoryNavigation:
    """Tests for directory navigation (current_directory, change_directory, list_directory)."""

    def test_current_directory_defaults_to_dollar(self):
        """Test current directory defaults to $."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        assert dfs.current_directory == "$"

    def test_change_directory(self):
        """Test changing current directory."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.change_directory("A")
        assert dfs.current_directory == "A"

        dfs.change_directory("$")
        assert dfs.current_directory == "$"

        dfs.change_directory("Z")
        assert dfs.current_directory == "Z"

    def test_change_directory_normalizes_case(self):
        """Test change_directory normalizes to uppercase."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.change_directory("a")
        assert dfs.current_directory == "A"

    def test_change_directory_invalid_raises(self):
        """Test change_directory raises error for invalid directory."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        with pytest.raises(ValueError, match="Directory must be single character"):
            dfs.change_directory("AB")

        with pytest.raises(ValueError, match="Invalid directory.*Must be"):
            dfs.change_directory("1")

        with pytest.raises(ValueError, match="Directory must be single character"):
            dfs.change_directory("")

    def test_list_directory_current(self):
        """Test listing files in current directory."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Add files to different directories
        dfs.save("$.FILE1", b"data1")
        dfs.save("$.FILE2", b"data2")
        dfs.save("A.FILE3", b"data3")
        dfs.save("B.FILE4", b"data4")

        # List current (default $)
        files = dfs.list_directory()
        assert len(files) == 2
        assert all(f.directory == "$" for f in files)
        assert {f.filename for f in files} == {"FILE1", "FILE2"}

    def test_list_directory_explicit(self):
        """Test listing files in explicitly specified directory."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.save("$.FILE1", b"data1")
        dfs.save("A.FILE2", b"data2")
        dfs.save("A.FILE3", b"data3")

        # List directory A
        files = dfs.list_directory("A")
        assert len(files) == 2
        assert all(f.directory == "A" for f in files)
        assert {f.filename for f in files} == {"FILE2", "FILE3"}

    def test_list_directory_respects_current(self):
        """Test list_directory respects current directory when not specified."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.save("$.FILE1", b"data1")
        dfs.save("A.FILE2", b"data2")

        # Change to directory A
        dfs.change_directory("A")

        # List without specifying directory should use current
        files = dfs.list_directory()
        assert len(files) == 1
        assert files[0].directory == "A"
        assert files[0].filename == "FILE2"

    def test_list_directory_empty(self):
        """Test listing empty directory."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.save("$.FILE1", b"data1")

        # List directory A (no files)
        files = dfs.list_directory("A")
        assert len(files) == 0


class TestDFSPythonicProtocols:
    """Tests for Pythonic protocols (__contains__, __iter__, __len__, __repr__, __str__)."""

    def test_contains_operator(self):
        """Test 'in' operator for file existence."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.save("$.EXISTS", b"data")

        assert "$.EXISTS" in dfs
        assert "$.NOSUCH" not in dfs

    def test_iteration(self):
        """Test iterating over files."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.save("$.FILE1", b"data1")
        dfs.save("$.FILE2", b"data2")
        dfs.save("A.FILE3", b"data3")

        # Iterate over files
        filenames = [f.filename for f in dfs]
        assert len(filenames) == 3
        assert set(filenames) == {"FILE1", "FILE2", "FILE3"}

    def test_len(self):
        """Test len() returns number of files."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        assert len(dfs) == 0

        dfs.save("$.FILE1", b"data")
        assert len(dfs) == 1

        dfs.save("$.FILE2", b"data")
        assert len(dfs) == 2

        dfs.delete("$.FILE1")
        assert len(dfs) == 1

    def test_repr(self):
        """Test repr() returns debug representation."""
        buffer = bytearray(102400)

        buffer[0:8] = b"TESTDISK"
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.save("$.FILE1", b"data")

        r = repr(dfs)
        assert "DFS(" in r
        assert "title='TESTDISK'" in r
        assert "files=1" in r
        assert "free_sectors=" in r

    def test_str(self):
        """Test str() returns user-friendly representation."""
        buffer = bytearray(102400)

        buffer[0:8] = b"MYDISK  "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        dfs.save("$.FILE1", b"data")
        dfs.save("$.FILE2", b"data")

        s = str(dfs)
        assert "MYDISK" in s
        assert "2 files" in s
        assert "sectors free" in s


class TestDFSIntegration:
    """Integration tests."""

    def test_full_workflow(self):
        """Test complete workflow: create disk, add files, rename, lock, delete."""
        buffer = bytearray(102400)

        # Empty catalog
        buffer[0:8] = b"TESTDISK"
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)

        # Add some files
        dfs.save("$.FILE1", b"Contents of file 1")
        dfs.save("$.FILE2", b"Contents of file 2")
        dfs.save("A.FILE3", b"Contents of file 3")

        assert len(dfs.files) == 3

        # Rename one
        dfs.rename("$.FILE1", "$.RENAMED")
        assert dfs.exists("$.RENAMED")
        assert not dfs.exists("$.FILE1")

        # Lock one
        dfs.lock("$.FILE2")
        assert dfs.files[1].locked == True

        # Delete unlocked file
        dfs.delete("$.RENAMED")
        assert len(dfs.files) == 2

        # Change metadata
        dfs.title = "MODIFIED"
        dfs.boot_option = 2

        assert dfs.title == "MODIFIED"
        assert dfs.boot_option == 2


class TestDFSFromFile:
    """Tests for from_file() and context manager."""

    def test_from_file_read_only(self):
        """Test opening a disc image file read-only."""
        with DFS.from_file(GAME_IMAGE_FILEPATH, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            assert len(dfs.files) == 4
            assert dfs.exists("$.!BOOT")

    def test_from_file_reads_title(self):
        """Test that disc title is read correctly from file."""
        with DFS.from_file(GAME_IMAGE_FILEPATH, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            assert dfs.title.rstrip("\x00").startswith("ZALAG")

    def test_from_file_load_file(self):
        """Test loading a file from a file-backed disc image."""
        with DFS.from_file(GAME_IMAGE_FILEPATH, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            data = dfs.load("$.!BOOT")
            assert len(data) > 0

    def test_from_file_read_write(self, tmp_path):
        """Test opening a disc image in read-write mode."""
        # Copy the game image to a temp location
        tmp_filepath = tmp_path / "test.ssd"
        shutil.copy2(GAME_IMAGE_FILEPATH, tmp_filepath)

        # Modify via mmap
        with DFS.from_file(tmp_filepath, ACORN_DFS_80T_SINGLE_SIDED, mode="r+b") as dfs:
            original_title = dfs.title
            dfs.title = "MODIFIED"
            assert dfs.title == "MODIFIED"

        # Re-open and verify the change persisted
        with DFS.from_file(tmp_filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            assert dfs.title == "MODIFIED"

    def test_from_file_invalid_mode(self):
        """Test that invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="mode must be"):
            with DFS.from_file(GAME_IMAGE_FILEPATH, ACORN_DFS_80T_SINGLE_SIDED, mode="wb"):
                pass

    def test_from_file_nonexistent(self):
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            with DFS.from_file("/nonexistent/disc.ssd", ACORN_DFS_80T_SINGLE_SIDED):
                pass

    def test_from_file_read_only_prevents_writes(self):
        """Test that read-only mode prevents modifications."""
        with DFS.from_file(GAME_IMAGE_FILEPATH, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            with pytest.raises(TypeError):
                dfs.title = "NOPE"

    def test_from_file_with_side(self, tmp_path):
        """Test from_file with side parameter for DSD images."""
        from oaknut_dfs.formats import ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED

        # Create a minimal DSD
        buf = bytearray(204800)
        buf[0:8] = b"SIDE0   "
        buf[256:260] = b"    "
        buf[262] = 0x00
        buf[263] = 200
        buf[2560:2568] = b"SIDE1   "
        buf[2560 + 256:2560 + 260] = b"    "
        buf[2560 + 262] = 0x00
        buf[2560 + 263] = 200

        tmp_filepath = tmp_path / "test.dsd"
        tmp_filepath.write_bytes(buf)

        with DFS.from_file(tmp_filepath, ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=0) as dfs0:
            assert dfs0.title == "SIDE0"

        with DFS.from_file(tmp_filepath, ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=1) as dfs1:
            assert dfs1.title == "SIDE1"

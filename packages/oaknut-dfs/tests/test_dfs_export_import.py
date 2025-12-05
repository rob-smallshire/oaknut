"""Tests for DFS export/import operations (.inf files)."""

import pytest
from pathlib import Path

from oaknut_dfs.dfs import DFS


class TestExportAll:
    """Tests for export_all()."""

    def test_export_all_with_metadata(self, tmp_path):
        """Test exporting all files with .inf metadata."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_ssd(memoryview(buffer))

        # Add some files
        dfs.save("$.FILE1", b"Contents 1", load_address=0x1900, exec_address=0x8023)
        dfs.save("$.FILE2", b"Contents 2", load_address=0x2000, exec_address=0x3000)
        dfs.save("A.FILE3", b"Contents 3", locked=True)

        # Export
        target = tmp_path / "export"
        dfs.export_all(str(target), preserve_metadata=True)

        # Check files were created
        assert (target / "$.FILE1").exists()
        assert (target / "$.FILE2").exists()
        assert (target / "A.FILE3").exists()

        # Check .inf files were created
        assert (target / "$.FILE1.inf").exists()
        assert (target / "$.FILE2.inf").exists()
        assert (target / "A.FILE3.inf").exists()

        # Check data
        assert (target / "$.FILE1").read_bytes() == b"Contents 1"
        assert (target / "$.FILE2").read_bytes() == b"Contents 2"
        assert (target / "A.FILE3").read_bytes() == b"Contents 3"

        # Check .inf content
        inf1 = (target / "$.FILE1.inf").read_text()
        assert "$.FILE1" in inf1
        assert "00001900" in inf1
        assert "00008023" in inf1
        assert "Locked" not in inf1

        inf3 = (target / "A.FILE3.inf").read_text()
        assert "$.FILE3" in inf3
        assert "Locked" in inf3

    def test_export_all_without_metadata(self, tmp_path):
        """Test exporting files without .inf metadata."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_ssd(memoryview(buffer))

        dfs.save("$.TEST", b"data")

        # Export without metadata
        target = tmp_path / "export"
        dfs.export_all(str(target), preserve_metadata=False)

        # Check file was created
        assert (target / "$.TEST").exists()

        # Check .inf file was NOT created
        assert not (target / "$.TEST.inf").exists()

    def test_export_all_creates_directory(self, tmp_path):
        """Test export_all creates target directory if it doesn't exist."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_ssd(memoryview(buffer))

        dfs.save("$.TEST", b"data")

        # Export to non-existent nested directory
        target = tmp_path / "nested" / "path" / "export"
        dfs.export_all(str(target))

        # Check directory was created
        assert target.exists()
        assert (target / "$.TEST").exists()

    def test_export_all_empty_disk(self, tmp_path):
        """Test exporting empty disk."""
        buffer = bytearray(102400)

        buffer[0:8] = b"EMPTY   "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_ssd(memoryview(buffer))

        # Export
        target = tmp_path / "export"
        dfs.export_all(str(target))

        # Directory should be created but empty
        assert target.exists()
        assert list(target.iterdir()) == []


class TestImportFromInf:
    """Tests for import_from_inf()."""

    def test_import_with_inf_file(self, tmp_path):
        """Test importing file with .inf metadata."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_ssd(memoryview(buffer))

        # Create test files
        data_file = tmp_path / "TEST"
        data_file.write_bytes(b"Test data")

        inf_file = tmp_path / "TEST.inf"
        inf_file.write_text("$.HELLO 00001900 00008023 00000009\n")

        # Import
        dfs.import_from_inf(str(data_file))

        # Check file was imported
        assert dfs.exists("$.HELLO")
        assert dfs.load("$.HELLO") == b"Test data"

        # Check metadata
        info = dfs.get_file_info("$.HELLO")
        assert info.load_address == 0x1900
        assert info.exec_address == 0x8023
        assert info.locked == False

    def test_import_with_locked_flag(self, tmp_path):
        """Test importing locked file."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_ssd(memoryview(buffer))

        # Create test files
        data_file = tmp_path / "TEST"
        data_file.write_bytes(b"data")

        inf_file = tmp_path / "TEST.inf"
        inf_file.write_text("$.LOCKED 00001900 00008023 00000004 Locked\n")

        # Import
        dfs.import_from_inf(str(data_file))

        # Check file is locked
        info = dfs.get_file_info("$.LOCKED")
        assert info.locked == True

    def test_import_without_inf_file(self, tmp_path):
        """Test importing file without .inf uses defaults."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_ssd(memoryview(buffer))

        # Create test file without .inf
        data_file = tmp_path / "MYFILE"
        data_file.write_bytes(b"data")

        # Import
        dfs.import_from_inf(str(data_file))

        # Check file was imported with defaults
        assert dfs.exists("$.MYFILE")
        assert dfs.load("$.MYFILE") == b"data"

        # Check default metadata
        info = dfs.get_file_info("$.MYFILE")
        assert info.load_address == 0
        assert info.exec_address == 0
        assert info.locked == False

    def test_import_with_explicit_inf_path(self, tmp_path):
        """Test importing with explicitly specified .inf path."""
        buffer = bytearray(102400)

        buffer[0:8] = b"DISK    "
        buffer[256:260] = b"    "
        buffer[260] = 0
        buffer[261] = 0
        buffer[262] = 0x00
        buffer[263] = 200

        dfs = DFS.from_ssd(memoryview(buffer))

        # Create files in different locations
        data_file = tmp_path / "data" / "FILE"
        data_file.parent.mkdir()
        data_file.write_bytes(b"data")

        inf_file = tmp_path / "metadata" / "FILE.inf"
        inf_file.parent.mkdir()
        inf_file.write_text("$.CUSTOM 00001900 00008023 00000004\n")

        # Import with explicit inf path
        dfs.import_from_inf(str(data_file), str(inf_file))

        # Check file was imported with metadata from explicit path
        assert dfs.exists("$.CUSTOM")
        info = dfs.get_file_info("$.CUSTOM")
        assert info.load_address == 0x1900


class TestExportImportRoundTrip:
    """Tests for export/import round-trip."""

    def test_round_trip_preserves_everything(self, tmp_path):
        """Test exporting and re-importing preserves all data and metadata."""
        # Create original disk
        buffer1 = bytearray(102400)
        buffer1[0:8] = b"ORIG    "
        buffer1[256:260] = b"    "
        buffer1[260] = 0
        buffer1[261] = 0
        buffer1[262] = 0x00
        buffer1[263] = 200

        dfs1 = DFS.from_ssd(memoryview(buffer1))

        # Add files with various metadata
        dfs1.save("$.PROG", b"Program code", load_address=0x1900, exec_address=0x8023)
        dfs1.save("$.DATA", b"Data file", load_address=0x2000, exec_address=0x2000)
        dfs1.save("$.LOCKED", b"Protected", locked=True)
        dfs1.save("A.FILE", b"In directory A")

        # Export
        export_path = tmp_path / "export"
        dfs1.export_all(str(export_path))

        # Create new disk and import
        buffer2 = bytearray(102400)
        buffer2[0:8] = b"NEW     "
        buffer2[256:260] = b"    "
        buffer2[260] = 0
        buffer2[261] = 0
        buffer2[262] = 0x00
        buffer2[263] = 200

        dfs2 = DFS.from_ssd(memoryview(buffer2))

        # Import all files
        for filepath in export_path.glob("*"):
            if not filepath.name.endswith(".inf"):
                dfs2.import_from_inf(str(filepath))

        # Verify all files exist
        assert dfs2.exists("$.PROG")
        assert dfs2.exists("$.DATA")
        assert dfs2.exists("$.LOCKED")
        assert dfs2.exists("$.FILE")  # Note: directory info is in .inf, not filename

        # Verify data
        assert dfs2.load("$.PROG") == b"Program code"
        assert dfs2.load("$.DATA") == b"Data file"
        assert dfs2.load("$.LOCKED") == b"Protected"
        assert dfs2.load("$.FILE") == b"In directory A"

        # Verify metadata
        prog_info = dfs2.get_file_info("$.PROG")
        assert prog_info.load_address == 0x1900
        assert prog_info.exec_address == 0x8023

        locked_info = dfs2.get_file_info("$.LOCKED")
        assert locked_info.locked == True

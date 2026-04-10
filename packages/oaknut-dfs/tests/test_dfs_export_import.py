"""Tests for DFS export/import operations (.inf files)."""

import pytest
from oaknut_file import MetaFormat

from oaknut_dfs.dfs import DFS
from oaknut_dfs.formats import (
    ACORN_DFS_40T_SINGLE_SIDED,
)


def _make_dfs(buffer):
    """Create a DFS instance from a pre-initialised buffer."""
    return DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)


def _blank_buffer(title=b"DISK    "):
    """Return a 100K bytearray initialised as an empty DFS disc."""
    buffer = bytearray(102400)
    buffer[0:8] = title
    buffer[256:260] = b"    "
    buffer[260] = 0
    buffer[261] = 0
    buffer[262] = 0x00
    buffer[263] = 200
    return buffer


class TestExportFile:
    """Tests for export_file()."""

    def test_export_file_with_metadata(self, tmp_path):
        """Test exporting single file with .inf metadata."""
        dfs = _make_dfs(_blank_buffer())

        # Add a file
        (dfs.root / "$" / "HELLO").write_bytes(
            b"Hello World", load_address=0x1900, exec_address=0x8023
        )

        # Export single file
        target_file = tmp_path / "HELLO.bin"
        (dfs.root / "$" / "HELLO").export_file(target_file)

        # Check file was created
        assert target_file.exists()
        assert target_file.read_bytes() == b"Hello World"

        # Check .inf file was created
        inf_file = tmp_path / "HELLO.bin.inf"
        assert inf_file.exists()
        inf_content = inf_file.read_text()
        assert "$.HELLO" in inf_content
        assert "00001900" in inf_content
        assert "00008023" in inf_content

    def test_export_file_without_metadata(self, tmp_path):
        """Test exporting file without .inf metadata."""
        dfs = _make_dfs(_blank_buffer())

        (dfs.root / "$" / "TEST").write_bytes(b"data")

        # Export without metadata
        target_file = tmp_path / "test.bin"
        (dfs.root / "$" / "TEST").export_file(target_file, meta_format=None)

        # Check file was created
        assert target_file.exists()
        assert target_file.read_bytes() == b"data"

        # Check .inf file was NOT created
        assert not (tmp_path / "test.bin.inf").exists()

    def test_export_file_nonexistent_raises(self, tmp_path):
        """Test exporting nonexistent file raises error."""
        dfs = _make_dfs(_blank_buffer())

        with pytest.raises(FileNotFoundError):
            (dfs.root / "$" / "NOSUCH").export_file(tmp_path / "file.bin")

    def test_export_file_creates_parent_directories(self, tmp_path):
        """Test export_file creates parent directories if needed."""
        dfs = _make_dfs(_blank_buffer())

        (dfs.root / "$" / "FILE").write_bytes(b"data")

        # Export to nested path
        target_file = tmp_path / "nested" / "path" / "file.bin"
        (dfs.root / "$" / "FILE").export_file(target_file)

        # Check file was created
        assert target_file.exists()
        assert target_file.read_bytes() == b"data"


class TestExportAll:
    """Tests for export_all()."""

    def test_export_all_with_metadata(self, tmp_path):
        """Test exporting all files with .inf metadata."""
        dfs = _make_dfs(_blank_buffer())

        # Add some files
        (dfs.root / "$" / "FILE1").write_bytes(
            b"Contents 1", load_address=0x1900, exec_address=0x8023
        )
        (dfs.root / "$" / "FILE2").write_bytes(
            b"Contents 2", load_address=0x2000, exec_address=0x3000
        )
        (dfs.root / "A" / "FILE3").write_bytes(b"Contents 3", locked=True)

        # Export
        target = tmp_path / "export"
        dfs.export_all(str(target))

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

        # Regression: files in non-$ directories must record their real
        # directory in the INF filename field, not "$.NAME".
        inf3 = (target / "A.FILE3.inf").read_text()
        assert "A.FILE3" in inf3
        assert "$.FILE3" not in inf3
        # Locked bit is recorded as an attribute hex byte.
        attr_byte = int(inf3.split()[-1], 16)
        assert attr_byte & 0x08  # Access.L

    def test_export_all_without_metadata(self, tmp_path):
        """Test exporting files without .inf metadata."""
        dfs = _make_dfs(_blank_buffer())

        (dfs.root / "$" / "TEST").write_bytes(b"data")

        # Export without metadata
        target = tmp_path / "export"
        dfs.export_all(str(target), meta_format=None)

        # Check file was created
        assert (target / "$.TEST").exists()

        # Check .inf file was NOT created
        assert not (target / "$.TEST.inf").exists()

    def test_export_all_creates_directory(self, tmp_path):
        """Test export_all creates target directory if it doesn't exist."""
        dfs = _make_dfs(_blank_buffer())

        (dfs.root / "$" / "TEST").write_bytes(b"data")

        # Export to non-existent nested directory
        target = tmp_path / "nested" / "path" / "export"
        dfs.export_all(str(target))

        # Check directory was created
        assert target.exists()
        assert (target / "$.TEST").exists()

    def test_export_all_empty_disk(self, tmp_path):
        """Test exporting empty disk."""
        dfs = _make_dfs(_blank_buffer(title=b"EMPTY   "))

        # Export
        target = tmp_path / "export"
        dfs.export_all(str(target))

        # Directory should be created but empty
        assert target.exists()
        assert list(target.iterdir()) == []


class TestImportFromInf:
    """Tests for import_file()."""

    def test_import_with_inf_file(self, tmp_path):
        """Test importing file with .inf metadata."""
        dfs = _make_dfs(_blank_buffer())

        # Create test files
        data_file = tmp_path / "TEST"
        data_file.write_bytes(b"Test data")

        inf_file = tmp_path / "TEST.inf"
        inf_file.write_text("$.HELLO 00001900 00008023 00000009\n")

        # Import — the .inf says $.HELLO, but DFSPath uses the path explicitly
        (dfs.root / "$" / "HELLO").import_file(data_file)

        # Check file was imported
        assert (dfs.root / "$" / "HELLO").exists()
        assert (dfs.root / "$" / "HELLO").read_bytes() == b"Test data"

        # Check metadata
        info = (dfs.root / "$" / "HELLO").stat()
        assert info.load_address == 0x1900
        assert info.exec_address == 0x8023
        assert not info.locked

    def test_import_with_locked_flag(self, tmp_path):
        """Test importing locked file."""
        dfs = _make_dfs(_blank_buffer())

        # Create test files
        data_file = tmp_path / "TEST"
        data_file.write_bytes(b"data")

        inf_file = tmp_path / "TEST.inf"
        inf_file.write_text("$.LOCKED 00001900 00008023 00000004 Locked\n")

        # Import
        (dfs.root / "$" / "LOCKED").import_file(data_file)

        # Check file is locked
        info = (dfs.root / "$" / "LOCKED").stat()
        assert info.locked

    def test_import_without_inf_file(self, tmp_path):
        """Test importing file without .inf uses defaults."""
        dfs = _make_dfs(_blank_buffer())

        # Create test file without .inf
        data_file = tmp_path / "MYFILE"
        data_file.write_bytes(b"data")

        # Import — no .inf, so defaults are used
        (dfs.root / "$" / "MYFILE").import_file(data_file)

        # Check file was imported with defaults
        assert (dfs.root / "$" / "MYFILE").exists()
        assert (dfs.root / "$" / "MYFILE").read_bytes() == b"data"

        # Check default metadata
        info = (dfs.root / "$" / "MYFILE").stat()
        assert info.load_address == 0
        assert info.exec_address == 0
        assert not info.locked

    def test_import_with_sibling_inf(self, tmp_path):
        """Test that a sibling .inf is picked up when present."""
        dfs = _make_dfs(_blank_buffer())

        data_file = tmp_path / "FILE"
        data_file.write_bytes(b"data")
        (tmp_path / "FILE.inf").write_text("$.CUSTOM 00001900 00008023 00000004\n")

        (dfs.root / "$" / "CUSTOM").import_file(data_file)

        assert (dfs.root / "$" / "CUSTOM").exists()
        info = (dfs.root / "$" / "CUSTOM").stat()
        assert info.load_address == 0x1900


class TestExportImportRoundTrip:
    """Tests for export/import round-trip."""

    def test_round_trip_preserves_everything(self, tmp_path):
        """Test exporting and re-importing preserves all data and metadata.

        Now that export_all records the real DFS directory in each INF
        filename field, the INF can be parsed to recover the original
        DFS path directly.
        """
        dfs1 = _make_dfs(_blank_buffer(title=b"ORIG    "))

        (dfs1.root / "$" / "PROG").write_bytes(
            b"Program code", load_address=0x1900, exec_address=0x8023
        )
        (dfs1.root / "$" / "DATA").write_bytes(
            b"Data file", load_address=0x2000, exec_address=0x2000
        )
        (dfs1.root / "$" / "LOCKED").write_bytes(b"Protected", locked=True)
        (dfs1.root / "A" / "FILE").write_bytes(b"In directory A")

        export_path = tmp_path / "export"
        dfs1.export_all(str(export_path))

        dfs2 = _make_dfs(_blank_buffer(title=b"NEW     "))

        for filepath in export_path.glob("*"):
            if filepath.name.endswith(".inf"):
                continue
            inf_path = filepath.with_suffix(filepath.suffix + ".inf")
            inf_text = inf_path.read_text().strip()
            dfs_name = inf_text.split()[0]  # e.g. "$.PROG" or "A.FILE"
            directory, filename = dfs_name.split(".")
            (dfs2.root / directory / filename).import_file(filepath)

        assert (dfs2.root / "$" / "PROG").exists()
        assert (dfs2.root / "$" / "DATA").exists()
        assert (dfs2.root / "$" / "LOCKED").exists()
        assert (dfs2.root / "A" / "FILE").exists()

        assert (dfs2.root / "$" / "PROG").read_bytes() == b"Program code"
        assert (dfs2.root / "$" / "DATA").read_bytes() == b"Data file"
        assert (dfs2.root / "$" / "LOCKED").read_bytes() == b"Protected"
        assert (dfs2.root / "A" / "FILE").read_bytes() == b"In directory A"

        prog_info = (dfs2.root / "$" / "PROG").stat()
        assert prog_info.load_address == 0x1900
        assert prog_info.exec_address == 0x8023

        locked_info = (dfs2.root / "$" / "LOCKED").stat()
        assert locked_info.locked


class TestMetaFormatRoundTrip:
    """Per-format smoke tests — DFSPath.export_file / import_file."""

    @pytest.mark.parametrize(
        "fmt",
        [
            MetaFormat.INF_TRAD,
            MetaFormat.INF_PIEB,
            MetaFormat.FILENAME_RISCOS,
            MetaFormat.FILENAME_MOS,
        ],
    )
    def test_dfs_round_trip_per_format(self, tmp_path, fmt):
        """DFSPath export/import round-trip for each non-xattr MetaFormat."""
        dfs1 = _make_dfs(_blank_buffer())
        (dfs1.root / "$" / "PROG").write_bytes(
            b"code", load_address=0x1900, exec_address=0x8023
        )

        target = tmp_path / "PROG"
        written = (dfs1.root / "$" / "PROG").export_file(target, meta_format=fmt)
        assert written.read_bytes() == b"code"

        dfs2 = _make_dfs(_blank_buffer())
        (dfs2.root / "$" / "PROG").import_file(written, meta_formats=(fmt,))

        assert (dfs2.root / "$" / "PROG").read_bytes() == b"code"
        stat = (dfs2.root / "$" / "PROG").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023

    def test_dfs_locked_round_trip_inf_trad(self, tmp_path):
        """Locked bit survives INF_TRAD round-trip."""
        dfs1 = _make_dfs(_blank_buffer())
        (dfs1.root / "$" / "SEC").write_bytes(b"secret", locked=True)

        target = tmp_path / "SEC"
        (dfs1.root / "$" / "SEC").export_file(target)

        dfs2 = _make_dfs(_blank_buffer())
        (dfs2.root / "$" / "SEC").import_file(target)
        assert (dfs2.root / "$" / "SEC").stat().locked

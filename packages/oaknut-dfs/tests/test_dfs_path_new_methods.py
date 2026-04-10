"""Tests for new DFSPath methods: write_text(), export_file(), import_file()."""

import pytest

from oaknut_dfs.dfs import DFS, DFSPath
from oaknut_dfs.formats import ACORN_DFS_40T_SINGLE_SIDED


def _make_empty_dfs():
    buffer = bytearray(102400)
    buffer[0:8] = b"TESTDISC"
    buffer[256:260] = b"    "
    buffer[261] = 0
    buffer[263] = 200
    return DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)


class TestWriteText:

    def test_write_text_default_encoding(self):
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "TEXT").write_text("Hello")
        assert (dfs.root / "$" / "TEXT").read_bytes() == b"Hello"

    def test_write_text_acorn_encoding(self):
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "TEXT").write_text("\u00a3", encoding="acorn")  # £
        assert (dfs.root / "$" / "TEXT").read_bytes() == b"\x60"

    def test_write_text_with_metadata(self):
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "DOC").write_text(
            "Notes", load_address=0x1900, exec_address=0x8023,
        )
        stat = (dfs.root / "$" / "DOC").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023


class TestReadText:

    def test_read_text_default_acorn_encoding(self):
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "TEXT").write_text("Hello")
        assert (dfs.root / "$" / "TEXT").read_text() == "Hello"

    def test_read_text_pound_sign(self):
        """The pound sign round-trips via Acorn encoding (0x60)."""
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "PRICE").write_text("\u00a3")  # £
        assert (dfs.root / "$" / "PRICE").read_text() == "\u00a3"

    def test_read_text_explicit_encoding(self):
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "UTF").write_bytes("Héllo".encode("utf-8"))
        assert (dfs.root / "$" / "UTF").read_text(encoding="utf-8") == "Héllo"


class TestExportFile:

    def test_export_file_writes_data(self, tmp_path):
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "HELLO").write_bytes(b"Hello!")
        target = tmp_path / "HELLO"
        (dfs.root / "$" / "HELLO").export_file(target)
        assert target.read_bytes() == b"Hello!"

    def test_export_file_writes_inf(self, tmp_path):
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "CODE").write_bytes(
            b"\x00" * 100, load_address=0x1900, exec_address=0x8023, locked=True,
        )
        target = tmp_path / "CODE"
        (dfs.root / "$" / "CODE").export_file(target)

        inf = tmp_path / "CODE.inf"
        assert inf.exists()
        text = inf.read_text()
        assert "00001900" in text
        assert "00008023" in text

    def test_export_file_no_metadata(self, tmp_path):
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "PLAIN").write_bytes(b"data")
        target = tmp_path / "PLAIN"
        (dfs.root / "$" / "PLAIN").export_file(target, meta_format=None)
        assert target.read_bytes() == b"data"
        assert not (tmp_path / "PLAIN.inf").exists()


class TestImportFile:

    def test_import_file_reads_data(self, tmp_path):
        source = tmp_path / "hello.bin"
        source.write_bytes(b"Hello from host!")

        dfs = _make_empty_dfs()
        (dfs.root / "$" / "HELLO").import_file(source)
        assert (dfs.root / "$" / "HELLO").read_bytes() == b"Hello from host!"

    def test_import_file_with_inf(self, tmp_path):
        source = tmp_path / "code.bin"
        source.write_bytes(b"\x00" * 100)

        inf = tmp_path / "code.bin.inf"
        inf.write_text("$.ORIG 00001900 00008023 00000064 Locked\n")

        dfs = _make_empty_dfs()
        (dfs.root / "$" / "CODE").import_file(source)

        stat = (dfs.root / "$" / "CODE").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023
        assert stat.locked is True
        # Name comes from path, not .inf
        assert (dfs.root / "$" / "CODE").exists()

    def test_import_file_without_inf(self, tmp_path):
        source = tmp_path / "plain.bin"
        source.write_bytes(b"plain data")

        dfs = _make_empty_dfs()
        (dfs.root / "$" / "PLAIN").import_file(source)
        assert (dfs.root / "$" / "PLAIN").read_bytes() == b"plain data"
        stat = (dfs.root / "$" / "PLAIN").stat()
        assert stat.load_address == 0
        assert stat.exec_address == 0

    def test_import_file_sibling_inf(self, tmp_path):
        source = tmp_path / "data.bin"
        source.write_bytes(b"test")

        (tmp_path / "data.bin.inf").write_text(
            "$.IGNORED 0000FF00 0000FF00 00000004\n"
        )

        dfs = _make_empty_dfs()
        (dfs.root / "$" / "FILE").import_file(source)
        stat = (dfs.root / "$" / "FILE").stat()
        assert stat.load_address == 0xFF00


class TestExportImportRoundTrip:

    def test_export_then_import(self, tmp_path):
        dfs1 = _make_empty_dfs()
        original = bytes(range(200))
        (dfs1.root / "$" / "FILE").write_bytes(
            original, load_address=0x1900, exec_address=0x8023,
        )

        export_path = tmp_path / "FILE"
        (dfs1.root / "$" / "FILE").export_file(export_path)

        dfs2 = _make_empty_dfs()
        (dfs2.root / "$" / "FILE").import_file(export_path)

        assert (dfs2.root / "$" / "FILE").read_bytes() == original
        stat = (dfs2.root / "$" / "FILE").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023

"""Tests for ADFSPath.export_file() and import_file()."""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S

# Ensure acorn codec is registered
import oaknut_dfs.acorn_encoding  # noqa: F401


class TestExportFile:

    def test_export_file_writes_data(self, tmp_path):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Hello").write_bytes(b"Hello, World!")
        target = tmp_path / "Hello"
        (adfs.root / "Hello").export_file(target)
        assert target.read_bytes() == b"Hello, World!"

    def test_export_file_writes_inf(self, tmp_path):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Code").write_bytes(
            b"\x00" * 100,
            load_address=0x1900,
            exec_address=0x8023,
            locked=True,
        )
        target = tmp_path / "Code"
        (adfs.root / "Code").export_file(target)

        inf_filepath = tmp_path / "Code.inf"
        assert inf_filepath.exists()
        inf_text = inf_filepath.read_text()
        assert "00001900" in inf_text
        assert "00008023" in inf_text
        assert "L" in inf_text

    def test_export_file_no_metadata(self, tmp_path):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Plain").write_bytes(b"data")
        target = tmp_path / "Plain"
        (adfs.root / "Plain").export_file(target, preserve_metadata=False)
        assert target.read_bytes() == b"data"
        assert not (tmp_path / "Plain.inf").exists()

    def test_export_file_replaces_old_export_method(self):
        """The old export() method should no longer exist."""
        adfs = ADFS.create(ADFS_S)
        path = adfs.root / "Test"
        assert not hasattr(path, "export") or callable(getattr(path, "export_file"))


class TestImportFile:

    def test_import_file_reads_data(self, tmp_path):
        source = tmp_path / "hello.bin"
        source.write_bytes(b"Hello from host!")

        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Hello").import_file(source)
        assert (adfs.root / "Hello").read_bytes() == b"Hello from host!"

    def test_import_file_with_inf(self, tmp_path):
        source = tmp_path / "code.bin"
        source.write_bytes(b"\x00" * 100)

        inf = tmp_path / "code.bin.inf"
        inf.write_text("OrigName 00001900 00008023 00000064 L\n")

        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Code").import_file(source)

        # Metadata from .inf should be applied
        stat = (adfs.root / "Code").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023
        assert stat.locked is True
        # But the name comes from the ADFSPath, not the .inf
        assert (adfs.root / "Code").exists()

    def test_import_file_without_inf(self, tmp_path):
        source = tmp_path / "plain.bin"
        source.write_bytes(b"plain data")

        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Plain").import_file(source)
        assert (adfs.root / "Plain").read_bytes() == b"plain data"
        stat = (adfs.root / "Plain").stat()
        assert stat.load_address == 0
        assert stat.exec_address == 0

    def test_import_file_explicit_inf_path(self, tmp_path):
        source = tmp_path / "data.bin"
        source.write_bytes(b"test")

        inf = tmp_path / "metadata.inf"
        inf.write_text("Ignored 0000FF00 0000FF00 00000004\n")

        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").import_file(source, inf_filepath=inf)
        stat = (adfs.root / "File").stat()
        assert stat.load_address == 0xFF00

    def test_import_file_overwrite(self, tmp_path):
        source1 = tmp_path / "v1.bin"
        source1.write_bytes(b"version 1")
        source2 = tmp_path / "v2.bin"
        source2.write_bytes(b"version 2")

        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").import_file(source1)
        (adfs.root / "File").import_file(source2)
        assert (adfs.root / "File").read_bytes() == b"version 2"

    def test_import_file_into_subdirectory(self, tmp_path):
        source = tmp_path / "game.bin"
        source.write_bytes(b"game data")

        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games" / "Elite").import_file(source)
        assert (adfs.root / "Games" / "Elite").read_bytes() == b"game data"


class TestExportImportRoundTrip:

    def test_export_then_import_preserves_data(self, tmp_path):
        """Export a file and import it back — data should match."""
        adfs1 = ADFS.create(ADFS_S)
        original_data = bytes(range(256)) * 2
        (adfs1.root / "File").write_bytes(
            original_data,
            load_address=0x1900,
            exec_address=0x8023,
        )

        export_path = tmp_path / "File"
        (adfs1.root / "File").export_file(export_path)

        adfs2 = ADFS.create(ADFS_S)
        (adfs2.root / "File").import_file(export_path)

        assert (adfs2.root / "File").read_bytes() == original_data
        stat = (adfs2.root / "File").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023

    def test_export_then_import_locked_file(self, tmp_path):
        adfs1 = ADFS.create(ADFS_S)
        (adfs1.root / "Sec").write_bytes(b"secret", locked=True)

        export_path = tmp_path / "Sec"
        (adfs1.root / "Sec").export_file(export_path)

        adfs2 = ADFS.create(ADFS_S)
        (adfs2.root / "Sec").import_file(export_path)
        assert (adfs2.root / "Sec").stat().locked is True

"""Tests for the ZIP filesystem extension on the oaknut.filesystem axis."""

import zipfile

from oaknut.filesystem import (
    Confidence,
    Mount,
    create_filesystem,
    filesystem_names,
    identify,
    reader_for,
)


def _make_zip(tmp_path):
    archive_filepath = tmp_path / "data.zip"
    with zipfile.ZipFile(archive_filepath, "w") as archive:
        archive.writestr("hello.txt", "hi there")
        archive.writestr("dir/inner.dat", b"\x00\x01\x02")
    return archive_filepath


class TestRegistration:
    def test_zip_registered(self):
        assert "zip" in filesystem_names()


class TestProbe:
    def test_identifies_zip(self, tmp_path):
        results = identify(_make_zip(tmp_path))
        assert results[0].filesystem == "zip"
        assert results[0].confidence is Confidence.CERTAIN

    def test_rejects_non_zip(self):
        assert identify(b"not a zip at all" + b"\x00" * 100) == []


class TestMount:
    def test_lists_and_reads_members(self, tmp_path):
        filesystem = create_filesystem("zip")
        with reader_for(_make_zip(tmp_path)) as reader:
            mount = filesystem.open(reader)
            assert isinstance(mount, Mount)
            names = {entry.name for entry in mount.iter_entries("")}
            assert "hello.txt" in names
            assert mount.read_bytes("hello.txt") == b"hi there"
            assert mount.exists("dir/inner.dat")

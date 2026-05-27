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


class TestHierarchy:
    """iter_entries honours its path argument and the flat ZIP namespace is
    presented as a directory tree (synthesising directories the archive does
    not store explicitly)."""

    def test_root_lists_immediate_children_only(self, tmp_path):
        filesystem = create_filesystem("zip")
        with reader_for(_make_zip(tmp_path)) as reader:
            mount = filesystem.open(reader)
            root = {e.name: e for e in mount.iter_entries(mount.path_root())}
            # The nameless root has the file and the synthesised directory —
            # not the nested member dir/inner.dat.
            assert set(root) == {"hello.txt", "dir"}
            assert root["dir"].is_dir
            assert not root["hello.txt"].is_dir

    def test_subdirectory_lists_its_own_children(self, tmp_path):
        filesystem = create_filesystem("zip")
        with reader_for(_make_zip(tmp_path)) as reader:
            mount = filesystem.open(reader)
            inner = list(mount.iter_entries("dir"))
            assert [e.name for e in inner] == ["inner.dat"]
            assert inner[0].path == "dir/inner.dat"

    def test_stat_root_and_nested(self, tmp_path):
        filesystem = create_filesystem("zip")
        with reader_for(_make_zip(tmp_path)) as reader:
            mount = filesystem.open(reader)
            assert mount.stat(mount.path_root()).is_dir
            assert mount.exists(mount.path_root())
            assert mount.stat("dir").is_dir
            inner = mount.stat("dir/inner.dat")
            assert not inner.is_dir
            assert inner.length == 3

    def test_recursive_walk_terminates(self, tmp_path):
        # Regression: iter_entries used to ignore its path argument and
        # return the whole archive, so a tree-walk recursed forever.
        filesystem = create_filesystem("zip")
        with reader_for(_make_zip(tmp_path)) as reader:
            mount = filesystem.open(reader)
            seen: list[str] = []

            def walk(path: str) -> None:
                for entry in mount.iter_entries(path):
                    seen.append(entry.path)
                    if entry.is_dir:
                        walk(entry.path)

            walk(mount.path_root())
            assert set(seen) == {"hello.txt", "dir", "dir/inner.dat"}


class TestMetadata:
    """Acorn metadata recovered by oaknut-zip surfaces through the mount."""

    def test_acorn_metadata_surfaces(self, tmp_path):
        from oaknut.filesystem import AcornMetadata

        archive_filepath = tmp_path / "meta.zip"
        with zipfile.ZipFile(archive_filepath, "w") as archive:
            # A RISC OS filename-encoded member: the ",ff9" suffix is a
            # Sprite filetype that oaknut-zip decodes and strips.
            archive.writestr("Sprite,ff9", b"sprite data")
        filesystem = create_filesystem("zip")
        with reader_for(archive_filepath) as reader:
            mount = filesystem.open(reader)
            assert isinstance(mount, AcornMetadata)
            names = {e.name for e in mount.iter_entries(mount.path_root())}
            assert "Sprite" in names  # the ,ff9 suffix is stripped
            assert mount.acorn_meta("Sprite").infer_filetype() == 0xFF9
            # The clean name addresses the underlying suffixed member.
            assert mount.read_bytes("Sprite") == b"sprite data"

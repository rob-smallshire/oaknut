"""Tests for DFSPath — pathlib-inspired API for DFS."""

import pytest

from oaknut_dfs.dfs import DFS, DFSPath, DFSStat
from oaknut_dfs.formats import ACORN_DFS_40T_SINGLE_SIDED


def _make_empty_dfs():
    """Create a DFS instance with an empty catalogue."""
    buffer = bytearray(102400)  # 40T single-sided
    buffer[0:8] = b"TESTDISC"
    buffer[256:260] = b"    "
    buffer[260] = 0   # cycle
    buffer[261] = 0   # num_files * 8
    buffer[262] = 0x00
    buffer[263] = 200  # total sectors low byte (400 = 0x190)
    return DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)


def _make_dfs_with_files():
    """Create a DFS instance with files in $ and A directories."""
    dfs = _make_empty_dfs()
    dfs.save("$.HELLO", b"Hello, World!", load_address=0x1900, exec_address=0x8000)
    dfs.save("$.README", b"Read me please", load_address=0x2000)
    dfs.save("A.GAME", b"Game data here!", load_address=0x3000, exec_address=0x3000)
    return dfs


class TestDFSPathNavigation:

    def test_root(self):
        dfs = _make_empty_dfs()
        assert dfs.root.path == ""
        assert dfs.root.name == ""
        assert dfs.root.parts == ()

    def test_root_slash_directory(self):
        dfs = _make_empty_dfs()
        p = dfs.root / "$"
        assert p.path == "$"
        assert p.name == "$"
        assert p.parts == ("$",)

    def test_root_slash_dir_slash_file(self):
        dfs = _make_empty_dfs()
        p = dfs.root / "$" / "HELLO"
        assert p.path == "$.HELLO"
        assert p.name == "HELLO"
        assert p.parts == ("$", "HELLO")

    def test_parent_of_file(self):
        dfs = _make_empty_dfs()
        p = dfs.root / "$" / "HELLO"
        assert p.parent.path == "$"

    def test_parent_of_directory(self):
        dfs = _make_empty_dfs()
        p = dfs.root / "$"
        assert p.parent.path == ""

    def test_parent_of_root(self):
        dfs = _make_empty_dfs()
        assert dfs.root.parent.path == ""

    def test_path_factory(self):
        dfs = _make_empty_dfs()
        p = dfs.path("$.HELLO")
        assert p.path == "$.HELLO"


class TestDFSPathQuerying:

    def test_root_exists(self):
        dfs = _make_empty_dfs()
        assert dfs.root.exists()

    def test_root_is_dir(self):
        dfs = _make_empty_dfs()
        assert dfs.root.is_dir()
        assert not dfs.root.is_file()

    def test_directory_exists_when_populated(self):
        dfs = _make_dfs_with_files()
        assert (dfs.root / "$").exists()
        assert (dfs.root / "A").exists()

    def test_directory_not_exists_when_empty(self):
        dfs = _make_dfs_with_files()
        assert not (dfs.root / "B").exists()

    def test_directory_is_dir(self):
        dfs = _make_dfs_with_files()
        assert (dfs.root / "$").is_dir()
        assert not (dfs.root / "$").is_file()

    def test_file_exists(self):
        dfs = _make_dfs_with_files()
        assert (dfs.root / "$" / "HELLO").exists()

    def test_file_not_exists(self):
        dfs = _make_dfs_with_files()
        assert not (dfs.root / "$" / "MISSING").exists()

    def test_file_is_file(self):
        dfs = _make_dfs_with_files()
        assert (dfs.root / "$" / "HELLO").is_file()
        assert not (dfs.root / "$" / "HELLO").is_dir()

    def test_stat_file(self):
        dfs = _make_dfs_with_files()
        stat = (dfs.root / "$" / "HELLO").stat()
        assert isinstance(stat, DFSStat)
        assert stat.length == 13
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8000
        assert stat.is_directory is False
        assert stat.locked is False

    def test_stat_directory(self):
        dfs = _make_dfs_with_files()
        stat = (dfs.root / "$").stat()
        assert stat.is_directory is True

    def test_stat_root(self):
        dfs = _make_empty_dfs()
        stat = dfs.root.stat()
        assert stat.is_directory is True


class TestDFSPathIterdir:

    def test_iterdir_root_empty(self):
        dfs = _make_empty_dfs()
        entries = list(dfs.root)
        assert entries == []

    def test_iterdir_root(self):
        dfs = _make_dfs_with_files()
        entries = list(dfs.root)
        names = [e.name for e in entries]
        assert "$" in names
        assert "A" in names

    def test_iterdir_root_only_populated(self):
        dfs = _make_dfs_with_files()
        entries = list(dfs.root)
        # Should only have $ and A, not B through Z
        assert len(entries) == 2

    def test_iterdir_directory(self):
        dfs = _make_dfs_with_files()
        entries = list(dfs.root / "$")
        names = [e.name for e in entries]
        assert "HELLO" in names
        assert "README" in names
        assert len(names) == 2

    def test_iterdir_other_directory(self):
        dfs = _make_dfs_with_files()
        entries = list(dfs.root / "A")
        assert len(entries) == 1
        assert entries[0].name == "GAME"

    def test_iterdir_returns_dfspath(self):
        dfs = _make_dfs_with_files()
        entries = list(dfs.root / "$")
        assert all(isinstance(e, DFSPath) for e in entries)

    def test_iterdir_file_paths_correct(self):
        dfs = _make_dfs_with_files()
        entries = list(dfs.root / "A")
        assert entries[0].path == "A.GAME"


class TestDFSPathWalk:

    def test_walk_root(self):
        dfs = _make_dfs_with_files()
        results = list(dfs.root.walk())

        # Root yields directories, then each directory yields files
        assert len(results) == 3  # root + $ + A

        root_path, root_dirs, root_files = results[0]
        assert root_path.path == ""
        assert "$" in root_dirs
        assert "A" in root_dirs
        assert root_files == []

    def test_walk_finds_files(self):
        dfs = _make_dfs_with_files()
        results = list(dfs.root.walk())

        # Find the $ directory entry
        dollar_entries = [r for r in results if r[0].path == "$"]
        assert len(dollar_entries) == 1
        _, dirs, files = dollar_entries[0]
        assert dirs == []
        assert "HELLO" in files
        assert "README" in files

    def test_walk_directory(self):
        dfs = _make_dfs_with_files()
        results = list((dfs.root / "$").walk())

        assert len(results) == 1
        dirpath, dirs, files = results[0]
        assert dirpath.path == "$"
        assert dirs == []
        assert "HELLO" in files

    def test_walk_empty_disc(self):
        dfs = _make_empty_dfs()
        results = list(dfs.root.walk())
        assert len(results) == 1
        _, dirs, files = results[0]
        assert dirs == []
        assert files == []


class TestDFSPathFileOperations:

    def test_read_bytes(self):
        dfs = _make_dfs_with_files()
        data = (dfs.root / "$" / "HELLO").read_bytes()
        assert data == b"Hello, World!"

    def test_read_bytes_other_dir(self):
        dfs = _make_dfs_with_files()
        data = (dfs.root / "A" / "GAME").read_bytes()
        assert data == b"Game data here!"

    def test_read_bytes_directory_raises(self):
        dfs = _make_dfs_with_files()
        with pytest.raises(ValueError, match="directory"):
            (dfs.root / "$").read_bytes()

    def test_read_bytes_root_raises(self):
        dfs = _make_empty_dfs()
        with pytest.raises(ValueError, match="directory"):
            dfs.root.read_bytes()

    def test_read_nonexistent_raises(self):
        dfs = _make_dfs_with_files()
        with pytest.raises(FileNotFoundError):
            (dfs.root / "$" / "MISSING").read_bytes()

    def test_write_bytes(self):
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "NEWFILE").write_bytes(
            b"new data", load_address=0x1234
        )
        data = (dfs.root / "$" / "NEWFILE").read_bytes()
        assert data == b"new data"
        assert (dfs.root / "$" / "NEWFILE").stat().load_address == 0x1234

    def test_write_bytes_to_directory_raises(self):
        dfs = _make_empty_dfs()
        with pytest.raises(ValueError, match="directory"):
            (dfs.root / "$").write_bytes(b"data")


class TestDFSPathModification:

    def test_unlink(self):
        dfs = _make_dfs_with_files()
        assert (dfs.root / "$" / "HELLO").exists()
        (dfs.root / "$" / "HELLO").unlink()
        assert not (dfs.root / "$" / "HELLO").exists()

    def test_unlink_directory_raises(self):
        dfs = _make_dfs_with_files()
        with pytest.raises(ValueError, match="directory"):
            (dfs.root / "$").unlink()

    def test_lock_and_unlock(self):
        dfs = _make_dfs_with_files()
        p = dfs.root / "$" / "HELLO"
        assert not p.stat().locked
        p.lock()
        assert p.stat().locked
        p.unlock()
        assert not p.stat().locked

    def test_rename(self):
        dfs = _make_dfs_with_files()
        old = dfs.root / "$" / "HELLO"
        new = old.rename("$.HOWDY")
        assert new.path == "$.HOWDY"
        assert not old.exists()
        assert new.exists()
        assert new.read_bytes() == b"Hello, World!"


class TestDFSPathContains:

    def test_root_contains_directory(self):
        dfs = _make_dfs_with_files()
        assert "$" in dfs.root
        assert "A" in dfs.root
        assert "B" not in dfs.root

    def test_directory_contains_file(self):
        dfs = _make_dfs_with_files()
        dollar = dfs.root / "$"
        assert "HELLO" in dollar
        assert "MISSING" not in dollar


class TestDFSPathEquality:

    def test_equal_paths(self):
        dfs = _make_empty_dfs()
        p1 = dfs.root / "$" / "HELLO"
        p2 = dfs.root / "$" / "HELLO"
        assert p1 == p2

    def test_case_insensitive(self):
        dfs = _make_empty_dfs()
        p1 = dfs.root / "$" / "HELLO"
        p2 = dfs.root / "$" / "hello"
        assert p1 == p2

    def test_hash_case_insensitive(self):
        dfs = _make_empty_dfs()
        p1 = dfs.root / "$" / "HELLO"
        p2 = dfs.root / "$" / "hello"
        assert hash(p1) == hash(p2)

    def test_repr(self):
        dfs = _make_empty_dfs()
        p = dfs.root / "$" / "HELLO"
        assert repr(p) == "DFSPath('$.HELLO')"

    def test_str(self):
        dfs = _make_empty_dfs()
        assert str(dfs.root) == ""
        assert str(dfs.root / "$") == "$"
        assert str(dfs.root / "$" / "HELLO") == "$.HELLO"

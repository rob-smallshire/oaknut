"""Tests for ADFSPath.rmdir() — removing empty directories."""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S, ADFS_M
from oaknut_dfs.exceptions import ADFSFileLockedError, ADFSPathError


class TestRmdir:

    def test_rmdir_empty_directory(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Empty").mkdir()
        (adfs.root / "Empty").rmdir()
        assert not (adfs.root / "Empty").exists()

    def test_rmdir_frees_sectors(self):
        adfs = ADFS.create(ADFS_S)
        free_before = adfs.free_space
        (adfs.root / "Dir").mkdir()
        assert adfs.free_space == free_before - 5 * 256
        (adfs.root / "Dir").rmdir()
        assert adfs.free_space == free_before

    def test_rmdir_removes_from_parent(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "A").mkdir()
        (adfs.root / "B").mkdir()
        (adfs.root / "A").rmdir()
        names = [p.name for p in adfs.root]
        assert names == ["B"]

    def test_rmdir_nonempty_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir" / "File").write_bytes(b"data")
        with pytest.raises(ADFSPathError, match="not empty"):
            (adfs.root / "Dir").rmdir()
        # Directory should still exist
        assert (adfs.root / "Dir").exists()

    def test_rmdir_nonempty_with_subdir_raises(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir" / "Sub").mkdir()
        with pytest.raises(ADFSPathError, match="not empty"):
            (adfs.root / "Dir").rmdir()

    def test_rmdir_locked_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir").lock()
        with pytest.raises(ADFSFileLockedError):
            (adfs.root / "Dir").rmdir()
        assert (adfs.root / "Dir").exists()

    def test_rmdir_nonexistent_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="not found"):
            (adfs.root / "Missing").rmdir()

    def test_rmdir_file_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        with pytest.raises(ADFSPathError, match="not a directory"):
            (adfs.root / "File").rmdir()

    def test_rmdir_root_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError):
            adfs.root.rmdir()

    def test_rmdir_nested(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "A").mkdir()
        (adfs.root / "A" / "B").mkdir()
        (adfs.root / "A" / "B").rmdir()
        assert (adfs.root / "A").exists()
        assert not (adfs.root / "A" / "B").exists()

    def test_validate_after_rmdir(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir").rmdir()
        assert adfs.validate() == []

    def test_rmdir_then_reuse_space(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir").rmdir()
        (adfs.root / "File").write_bytes(b"\x00" * 1024)
        assert (adfs.root / "File").read_bytes() == b"\x00" * 1024

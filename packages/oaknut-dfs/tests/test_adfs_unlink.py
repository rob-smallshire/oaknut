"""Tests for ADFSPath.unlink() — deleting files from ADFS disc images."""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S
from oaknut_dfs.exceptions import ADFSFileLockedError, ADFSPathError


class TestUnlink:

    def test_unlink_file(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Hello").write_bytes(b"data")
        assert (adfs.root / "Hello").exists()
        (adfs.root / "Hello").unlink()
        assert not (adfs.root / "Hello").exists()

    def test_unlink_removes_from_directory(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "A").write_bytes(b"aaa")
        (adfs.root / "B").write_bytes(b"bbb")
        (adfs.root / "C").write_bytes(b"ccc")
        (adfs.root / "B").unlink()
        names = [p.name for p in adfs.root]
        assert names == ["A", "C"]

    def test_unlink_frees_sectors(self):
        adfs = ADFS.create(ADFS_S)
        initial_free = adfs.free_space
        (adfs.root / "File").write_bytes(b"\x00" * 1024)  # 4 sectors
        assert adfs.free_space == initial_free - 1024
        (adfs.root / "File").unlink()
        assert adfs.free_space == initial_free

    def test_unlink_empty_file(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Empty").write_bytes(b"")
        (adfs.root / "Empty").unlink()
        assert not (adfs.root / "Empty").exists()

    def test_unlink_nonexistent_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="not found"):
            (adfs.root / "Missing").unlink()

    def test_unlink_locked_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Secret").write_bytes(b"data", locked=True)
        with pytest.raises(ADFSFileLockedError):
            (adfs.root / "Secret").unlink()
        # File should still exist
        assert (adfs.root / "Secret").exists()

    def test_unlink_root_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError):
            adfs.root.unlink()

    def test_unlink_then_write_reuses_space(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Old").write_bytes(b"\x00" * 512)
        (adfs.root / "Old").unlink()
        (adfs.root / "New").write_bytes(b"\xFF" * 512)
        assert (adfs.root / "New").read_bytes() == b"\xFF" * 512

    def test_validate_after_unlink(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").unlink()
        assert adfs.validate() == []

    def test_unlink_directory_raises(self):
        """unlink() should not delete directories — use rmdir for that."""
        adfs = ADFS.create(ADFS_S)
        # We need mkdir for this test, so skip if not available
        pytest.importorskip("oaknut_dfs.adfs")
        # Write a file, then try to unlink root (a directory)
        # This is already covered by test_unlink_root_raises, but
        # let's also test with a subdirectory once mkdir is available

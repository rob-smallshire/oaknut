"""Tests for ADFSPath.rename(), lock(), and unlock()."""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S
from oaknut_dfs.exceptions import ADFSFileLockedError, ADFSPathError


class TestRename:

    def test_rename_file(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Old").write_bytes(b"data")
        result = (adfs.root / "Old").rename(adfs.root / "New")
        assert not (adfs.root / "Old").exists()
        assert (adfs.root / "New").exists()
        assert (adfs.root / "New").read_bytes() == b"data"

    def test_rename_returns_new_path(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Old").write_bytes(b"data")
        result = (adfs.root / "Old").rename(adfs.root / "New")
        assert result.path == "$.New"

    def test_rename_accepts_string(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Old").write_bytes(b"data")
        result = (adfs.root / "Old").rename("$.New")
        assert (adfs.root / "New").read_bytes() == b"data"

    def test_rename_preserves_metadata(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Old").write_bytes(
            b"data", load_address=0x1900, exec_address=0x8023, locked=True,
        )
        (adfs.root / "Old").rename(adfs.root / "New")
        stat = (adfs.root / "New").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023
        assert stat.locked is True

    def test_rename_preserves_data_integrity(self):
        adfs = ADFS.create(ADFS_S)
        data = bytes(range(256)) * 4
        (adfs.root / "Old").write_bytes(data)
        (adfs.root / "Old").rename(adfs.root / "New")
        assert (adfs.root / "New").read_bytes() == data

    def test_rename_does_not_change_sector_allocation(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Old").write_bytes(b"\x00" * 512)
        free_before = adfs.free_space
        (adfs.root / "Old").rename(adfs.root / "New")
        assert adfs.free_space == free_before

    def test_rename_nonexistent_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="not found"):
            (adfs.root / "Missing").rename(adfs.root / "New")

    def test_rename_to_existing_name_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "First").write_bytes(b"one")
        (adfs.root / "Second").write_bytes(b"two")
        with pytest.raises(ADFSPathError, match="already exists"):
            (adfs.root / "First").rename(adfs.root / "Second")

    def test_rename_root_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError):
            adfs.root.rename("$.New")

    def test_rename_directory(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "OldDir").mkdir()
        (adfs.root / "OldDir" / "File").write_bytes(b"inside")
        (adfs.root / "OldDir").rename(adfs.root / "NewDir")
        assert not (adfs.root / "OldDir").exists()
        assert (adfs.root / "NewDir").is_dir()
        assert (adfs.root / "NewDir" / "File").read_bytes() == b"inside"

    def test_rename_preserves_other_files(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Keep").write_bytes(b"stay")
        (adfs.root / "Old").write_bytes(b"move")
        (adfs.root / "Old").rename(adfs.root / "New")
        assert (adfs.root / "Keep").read_bytes() == b"stay"

    def test_validate_after_rename(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Old").write_bytes(b"data")
        (adfs.root / "Old").rename(adfs.root / "New")
        assert adfs.validate() == []


class TestLock:

    def test_lock_file(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").lock()
        assert (adfs.root / "File").stat().locked is True

    def test_lock_already_locked(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data", locked=True)
        (adfs.root / "File").lock()  # Should be a no-op
        assert (adfs.root / "File").stat().locked is True

    def test_lock_nonexistent_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="not found"):
            (adfs.root / "Missing").lock()

    def test_lock_root_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError):
            adfs.root.lock()

    def test_lock_preserves_data(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"precious")
        (adfs.root / "File").lock()
        assert (adfs.root / "File").read_bytes() == b"precious"

    def test_locked_file_cannot_be_deleted(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").lock()
        with pytest.raises(ADFSFileLockedError):
            (adfs.root / "File").unlink()

    def test_validate_after_lock(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").lock()
        assert adfs.validate() == []


class TestUnlock:

    def test_unlock_file(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data", locked=True)
        (adfs.root / "File").unlock()
        assert (adfs.root / "File").stat().locked is False

    def test_unlock_already_unlocked(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").unlock()  # Should be a no-op
        assert (adfs.root / "File").stat().locked is False

    def test_unlock_nonexistent_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="not found"):
            (adfs.root / "Missing").unlock()

    def test_unlock_root_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError):
            adfs.root.unlock()

    def test_unlock_then_delete(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data", locked=True)
        (adfs.root / "File").unlock()
        (adfs.root / "File").unlink()
        assert not (adfs.root / "File").exists()

    def test_validate_after_unlock(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data", locked=True)
        (adfs.root / "File").unlock()
        assert adfs.validate() == []

"""Tests for ADFSPath.rename() across directories."""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S, ADFS_M
from oaknut_dfs.exceptions import ADFSPathError


class TestRenameCrossDirectory:

    def test_move_file_to_subdirectory(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Games").mkdir()
        (adfs.root / "Elite").write_bytes(b"game data")
        (adfs.root / "Elite").rename(adfs.root / "Games" / "Elite")
        assert not (adfs.root / "Elite").exists()
        assert (adfs.root / "Games" / "Elite").read_bytes() == b"game data"

    def test_move_file_to_root(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir" / "File").write_bytes(b"data")
        (adfs.root / "Dir" / "File").rename(adfs.root / "File")
        assert not (adfs.root / "Dir" / "File").exists()
        assert (adfs.root / "File").read_bytes() == b"data"

    def test_move_preserves_metadata(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Prog").write_bytes(
            b"code", load_address=0x1900, exec_address=0x8023, locked=True,
        )
        (adfs.root / "Prog").rename(adfs.root / "Dir" / "Prog")
        stat = (adfs.root / "Dir" / "Prog").stat()
        assert stat.load_address == 0x1900
        assert stat.exec_address == 0x8023
        assert stat.locked is True

    def test_move_preserves_data(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        data = bytes(range(256)) * 4
        (adfs.root / "Big").write_bytes(data)
        (adfs.root / "Big").rename(adfs.root / "Dir" / "Big")
        assert (adfs.root / "Dir" / "Big").read_bytes() == data

    def test_move_does_not_copy_data(self):
        """Cross-directory rename should not change free space (no data copy)."""
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "File").write_bytes(b"\x00" * 512)
        free_before = adfs.free_space
        (adfs.root / "File").rename(adfs.root / "Dir" / "File")
        assert adfs.free_space == free_before

    def test_move_and_rename_simultaneously(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "OldName").write_bytes(b"data")
        (adfs.root / "OldName").rename(adfs.root / "Dir" / "NewName")
        assert not (adfs.root / "OldName").exists()
        assert (adfs.root / "Dir" / "NewName").read_bytes() == b"data"

    def test_move_between_subdirectories(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Src").mkdir()
        (adfs.root / "Dst").mkdir()
        (adfs.root / "Src" / "File").write_bytes(b"moving")
        (adfs.root / "Src" / "File").rename(adfs.root / "Dst" / "File")
        assert not (adfs.root / "Src" / "File").exists()
        assert (adfs.root / "Dst" / "File").read_bytes() == b"moving"

    def test_move_to_existing_name_raises(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "File").write_bytes(b"source")
        (adfs.root / "Dir" / "File").write_bytes(b"target")
        with pytest.raises(ADFSPathError, match="already exists"):
            (adfs.root / "File").rename(adfs.root / "Dir" / "File")

    def test_move_to_nonexistent_directory_raises(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "File").write_bytes(b"data")
        with pytest.raises(ADFSPathError):
            (adfs.root / "File").rename(adfs.root / "Missing" / "File")

    def test_move_directory_into_subdirectory(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Parent").mkdir()
        (adfs.root / "Child").mkdir()
        (adfs.root / "Child" / "File").write_bytes(b"inside")
        (adfs.root / "Child").rename(adfs.root / "Parent" / "Child")
        assert not (adfs.root / "Child").exists()
        assert (adfs.root / "Parent" / "Child").is_dir()
        assert (adfs.root / "Parent" / "Child" / "File").read_bytes() == b"inside"

    def test_validate_after_cross_dir_rename(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "File").write_bytes(b"data")
        (adfs.root / "File").rename(adfs.root / "Dir" / "File")
        assert adfs.validate() == []

    def test_same_directory_rename_still_works(self):
        """Existing same-directory rename should not break."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Old").write_bytes(b"data")
        (adfs.root / "Old").rename(adfs.root / "New")
        assert (adfs.root / "New").read_bytes() == b"data"

    def test_returns_new_path(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "File").write_bytes(b"data")
        result = (adfs.root / "File").rename(adfs.root / "Dir" / "File")
        assert result.path == "$.Dir.File"

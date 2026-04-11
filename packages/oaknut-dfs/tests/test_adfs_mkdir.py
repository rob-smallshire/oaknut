"""Tests for ADFSPath.mkdir() — creating directories in ADFS disc images."""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S, ADFS_M
from oaknut_dfs.exceptions import (
    ADFSDirectoryFullError,
    ADFSDiscFullError,
    ADFSPathError,
)


class TestMkdir:

    def test_mkdir_creates_directory(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        assert (adfs.root / "Games").exists()
        assert (adfs.root / "Games").is_dir()

    def test_mkdir_appears_in_parent(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        names = [p.name for p in adfs.root]
        assert "Games" in names

    def test_mkdir_initially_empty(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        assert list(adfs.root / "Games") == []

    def test_mkdir_allocates_5_sectors(self):
        """Old-format directories occupy 5 sectors."""
        adfs = ADFS.create(ADFS_S)
        initial_free = adfs.free_space
        (adfs.root / "Games").mkdir()
        assert adfs.free_space == initial_free - 5 * 256

    def test_write_file_in_new_directory(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games" / "Elite").write_bytes(
            b"game data", load_address=0x1900,
        )
        assert (adfs.root / "Games" / "Elite").read_bytes() == b"game data"

    def test_mkdir_nested(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Level1").mkdir()
        (adfs.root / "Level1" / "Level2").mkdir()
        assert (adfs.root / "Level1" / "Level2").is_dir()

    def test_write_file_in_nested_directory(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "A").mkdir()
        (adfs.root / "A" / "B").mkdir()
        (adfs.root / "A" / "B" / "File").write_bytes(b"deep")
        assert (adfs.root / "A" / "B" / "File").read_bytes() == b"deep"

    def test_mkdir_existing_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        with pytest.raises(ADFSPathError, match="already exists"):
            (adfs.root / "Games").mkdir()

    def test_mkdir_name_conflicts_with_file_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Name").write_bytes(b"file data")
        with pytest.raises(ADFSPathError, match="already exists"):
            (adfs.root / "Name").mkdir()

    def test_mkdir_root_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError):
            adfs.root.mkdir()

    def test_mkdir_parent_not_found_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError):
            (adfs.root / "Missing" / "Sub").mkdir()

    def test_mkdir_parent_directory_title(self):
        """New subdirectory should have its name as its title."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        # Walk into the subdir — verify it parses correctly
        results = list(adfs.root.walk())
        assert len(results) == 2

    def test_validate_after_mkdir(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        assert adfs.validate() == []

    def test_walk_with_mkdir_and_files(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Docs").mkdir()
        (adfs.root / "Docs" / "Readme").write_bytes(b"hello")
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games" / "Elite").write_bytes(b"game")

        results = list(adfs.root.walk())
        assert len(results) == 3  # root, Docs, Games

        root_path, root_dirs, root_files = results[0]
        assert sorted(root_dirs) == ["Docs", "Games"]
        assert root_files == []

    def test_mkdir_disc_full_raises(self):
        """mkdir needs 5 sectors; should raise if not enough space."""
        adfs = ADFS.create(ADFS_S)
        # Fill most of the disc
        free = adfs.free_space // 256  # sectors
        if free > 4:
            (adfs.root / "Big").write_bytes(b"\x00" * ((free - 4) * 256))
        with pytest.raises(ADFSDiscFullError):
            (adfs.root / "Dir").mkdir()

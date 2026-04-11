"""Tests for ADFSPath.title property on directories."""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S, ADFS_M
from oaknut_dfs.exceptions import ADFSPathError


class TestDirectoryTitleGetter:

    def test_root_title(self):
        adfs = ADFS.create(ADFS_S, title="MyDisc")
        assert adfs.root.title == "MyDisc"

    def test_root_title_matches_disc_title(self):
        adfs = ADFS.create(ADFS_S, title="TestDisc")
        assert adfs.root.title == adfs.title

    def test_root_empty_title(self):
        adfs = ADFS.create(ADFS_S)
        assert adfs.root.title == ""

    def test_subdir_title_defaults_to_name(self):
        """mkdir sets the title to the directory name."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        assert (adfs.root / "Games").title == "Games"

    def test_nested_subdir_title(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Level1").mkdir()
        (adfs.root / "Level1" / "Level2").mkdir()
        assert (adfs.root / "Level1" / "Level2").title == "Level2"

    def test_title_on_file_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        with pytest.raises(ADFSPathError):
            _ = (adfs.root / "File").title


class TestDirectoryTitleSetter:

    def test_set_root_title(self):
        adfs = ADFS.create(ADFS_S)
        adfs.root.title = "NewTitle"
        assert adfs.root.title == "NewTitle"

    def test_set_root_title_matches_disc_title(self):
        """Setting root title via path should update disc title too."""
        adfs = ADFS.create(ADFS_S)
        adfs.root.title = "ViaPath"
        assert adfs.title == "ViaPath"

    def test_set_subdir_title(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games").title = "Game Collection"
        assert (adfs.root / "Games").title == "Game Collection"

    def test_set_subdir_title_does_not_change_name(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games").title = "Totally Different"
        # Name in parent directory is unchanged
        names = [p.name for p in adfs.root]
        assert "Games" in names

    def test_set_subdir_title_does_not_change_root_title(self):
        adfs = ADFS.create(ADFS_S, title="DiscTitle")
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games").title = "SubTitle"
        assert adfs.title == "DiscTitle"

    def test_set_nested_subdir_title(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "A").mkdir()
        (adfs.root / "A" / "B").mkdir()
        (adfs.root / "A" / "B").title = "Deep Title"
        assert (adfs.root / "A" / "B").title == "Deep Title"
        # Parent titles unaffected
        assert (adfs.root / "A").title == "A"

    def test_set_empty_title(self):
        adfs = ADFS.create(ADFS_S, title="OldTitle")
        adfs.root.title = ""
        assert adfs.root.title == ""

    def test_title_truncated_to_19_chars(self):
        adfs = ADFS.create(ADFS_S)
        adfs.root.title = "A" * 30
        assert len(adfs.root.title) <= 19

    def test_set_title_preserves_files(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        adfs.root.title = "Changed"
        assert (adfs.root / "File").read_bytes() == b"data"

    def test_set_title_preserves_subdirs(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir" / "File").write_bytes(b"inside")
        adfs.root.title = "Changed"
        assert (adfs.root / "Dir" / "File").read_bytes() == b"inside"

    def test_set_title_on_file_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        with pytest.raises(ADFSPathError):
            (adfs.root / "File").title = "Nope"

    def test_validate_after_title_change(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games").title = "New Title"
        assert adfs.validate() == []

    def test_title_round_trip_with_buffer(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games").title = "Persisted"

        buffer = adfs._disc._disc_image.buffer
        adfs2 = ADFS.from_buffer(buffer)
        assert (adfs2.root / "Games").title == "Persisted"

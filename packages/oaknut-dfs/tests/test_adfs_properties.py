"""Tests for ADFS title and boot_option property setters."""

import pytest

from oaknut_dfs.adfs import ADFS, ADFS_S


class TestTitleSetter:

    def test_set_title(self):
        adfs = ADFS.create(ADFS_S)
        adfs.title = "NewTitle"
        assert adfs.title == "NewTitle"

    def test_set_empty_title(self):
        adfs = ADFS.create(ADFS_S, title="OldTitle")
        adfs.title = ""
        assert adfs.title == ""

    def test_set_title_preserves_files(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        adfs.title = "Changed"
        assert adfs.title == "Changed"
        assert (adfs.root / "File").read_bytes() == b"data"

    def test_title_truncated_to_19_chars(self):
        adfs = ADFS.create(ADFS_S)
        adfs.title = "A" * 30
        assert len(adfs.title) <= 19

    def test_validate_after_title_change(self):
        adfs = ADFS.create(ADFS_S)
        adfs.title = "NewTitle"
        assert adfs.validate() == []

    def test_title_round_trip_with_buffer(self):
        adfs = ADFS.create(ADFS_S)
        adfs.title = "Persist"
        buffer = adfs._disc._disc_image.buffer
        adfs2 = ADFS.from_buffer(buffer)
        assert adfs2.title == "Persist"


class TestBootOptionSetter:

    def test_set_boot_option(self):
        adfs = ADFS.create(ADFS_S)
        adfs.boot_option = 3
        assert adfs.boot_option == 3

    def test_set_boot_option_zero(self):
        adfs = ADFS.create(ADFS_S, boot_option=2)
        adfs.boot_option = 0
        assert adfs.boot_option == 0

    def test_boot_option_invalid_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ValueError):
            adfs.boot_option = 4

    def test_boot_option_negative_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ValueError):
            adfs.boot_option = -1

    def test_validate_after_boot_option_change(self):
        adfs = ADFS.create(ADFS_S)
        adfs.boot_option = 2
        assert adfs.validate() == []

    def test_boot_option_preserves_files(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "File").write_bytes(b"data")
        adfs.boot_option = 1
        assert (adfs.root / "File").read_bytes() == b"data"

    def test_boot_option_round_trip_with_buffer(self):
        adfs = ADFS.create(ADFS_S)
        adfs.boot_option = 2
        buffer = adfs._disc._disc_image.buffer
        adfs2 = ADFS.from_buffer(buffer)
        assert adfs2.boot_option == 2

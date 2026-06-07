"""Validation and identification must descend the directory tree.

A disc whose root directory and free-space map are intact can still be
untraversable if a *subdirectory* is corrupt. Checking only the root (as
``validate`` once did) reports such a disc as clean and identifies it as
STRONG — false confidence that surfaces later as a parse error the moment
a command descends. Both gates therefore walk the tree.
"""

from oaknut.adfs import ADFS, ADFS_S
from oaknut.filesystem import Confidence, identify


def _image_with_corrupt_subdirectory(tmp_path):
    """An ADFS-S image whose one subdirectory has a smashed signature."""
    image_filepath = tmp_path / "broken.ads"
    with ADFS.create_file(str(image_filepath), ADFS_S, title="BROKEN") as adfs:
        (adfs.root / "SUBDIR").mkdir()
        # Locate the subdirectory on disc and smash its header signature,
        # leaving the root directory and free-space map untouched.
        root = adfs._read_root_directory()
        (subdir_entry,) = root.entries
        sector = adfs._disc.sector_range(subdir_entry.indirect_disc_address, 1)
        sector[0x01:0x05] = b"junk"
    return image_filepath


class TestValidateDescends:
    def test_clean_image_validates(self, tmp_path):
        image_filepath = tmp_path / "clean.ads"
        with ADFS.create_file(str(image_filepath), ADFS_S, title="CLEAN") as adfs:
            (adfs.root / "SUBDIR").mkdir()
        with ADFS.from_file(image_filepath) as adfs:
            assert adfs.validate() == []

    def test_corrupt_subdirectory_is_reported(self, tmp_path):
        image_filepath = _image_with_corrupt_subdirectory(tmp_path)
        with ADFS.from_file(image_filepath) as adfs:
            errors = adfs.validate()
        assert errors, "validate() should report the unreadable subdirectory"
        assert any("SUBDIR" in str(error) for error in errors)


class TestIdentifyDescends:
    def test_corrupt_subdirectory_is_not_strong(self, tmp_path):
        image_filepath = _image_with_corrupt_subdirectory(tmp_path)
        results = identify(image_filepath)
        adfs_results = [r for r in results if r.filesystem == "adfs"]
        assert adfs_results
        assert adfs_results[0].confidence is not Confidence.STRONG

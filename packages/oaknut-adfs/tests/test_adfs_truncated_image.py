"""A truncated ADFS image whose directory tree points past its end (#88).

The Master Compact Welcome capture holds only the first 1280 sectors of an
L-format disc, so two of its directories start beyond the image. Walking
the tree must treat such a directory as one it cannot read, as it does a
corrupt one, rather than let the out-of-bounds sector read escape: the walk
runs while identifying the disc, so an escaping error breaks every command.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from helpers.adfs_image import make_adfs_s_image, make_old_dir_entry
from oaknut.adfs import ADFS
from oaknut.adfs.exceptions import ADFSBeyondImageError, ADFSError
from oaknut.filesystem import fix_of, identify

from tests.fixtures import BEEBEM_IMAGES_DIRPATH, REFERENCE_IMAGES_DIRPATH

_WELCOME = REFERENCE_IMAGES_DIRPATH / "adfs-truncated" / "welcome-master-compact.adm"

#: The directories the Welcome capture is too short to hold.
_UNREACHABLE_DIRECTORIES = ["$.WIMPS.P", "$.WIMPS.R"]


def _image_with_a_directory_past_its_end() -> bytearray:
    """An ADFS-S image (640 sectors) whose one subdirectory is at sector 700."""
    entries = [
        make_old_dir_entry("Lost", length=1280, indirect_disc_address=700, is_directory=True)
    ]
    return make_adfs_s_image(root_entries=entries)


def _paths(errors) -> list[str]:
    return sorted(str(error).split(":")[0] for error in errors)


class TestDirectoryPastTheEnd:
    def test_is_a_traversal_error(self):
        adfs = ADFS.from_buffer(memoryview(_image_with_a_directory_past_its_end()))
        assert _paths(adfs._directory_tree_errors()) == ["$.Lost"]

    def test_is_reported_by_validate(self):
        adfs = ADFS.from_buffer(memoryview(_image_with_a_directory_past_its_end()))
        assert "$.Lost" in _paths(adfs.validate())


class TestWelcomeCapture:
    def test_walking_the_tree_reports_the_unreachable_directories(self):
        with ADFS.from_file(_WELCOME, read_only=True) as adfs:
            assert _paths(adfs._directory_tree_errors()) == _UNREACHABLE_DIRECTORIES

    def test_validate_reports_the_unreachable_directories(self):
        with ADFS.from_file(_WELCOME, read_only=True) as adfs:
            paths = _paths(adfs.validate())
        assert set(_UNREACHABLE_DIRECTORIES) <= set(paths)

    def test_is_identified_as_adfs(self):
        results = identify(_WELCOME)
        assert any(result.filesystem == "adfs" for result in results)


class TestReadingPastTheEnd:
    def test_a_file_wholly_past_the_end_is_a_data_error(self):
        with ADFS.from_file(_WELCOME, read_only=True) as adfs:
            with pytest.raises(ADFSBeyondImageError, match="past the end of the image"):
                adfs.path("$.LIBRARY.view").read_bytes()

    def test_a_file_running_past_the_end_is_a_data_error(self):
        with ADFS.from_file(_WELCOME, read_only=True) as adfs:
            with pytest.raises(ADFSBeyondImageError):
                adfs.path("$.WIMPS.Index1").read_bytes()

    def test_a_directory_past_the_end_is_a_data_error(self):
        with ADFS.from_file(_WELCOME, read_only=True) as adfs:
            with pytest.raises(ADFSBeyondImageError):
                list(adfs.path("$.WIMPS.P").iterdir())

    def test_the_error_is_an_adfs_error(self):
        assert issubclass(ADFSBeyondImageError, ADFSError)


#: Each object the Welcome capture cannot hold, and what its finding's fix does.
_WELCOME_FINDINGS = {
    "$.WIMPS.P": "remove $.WIMPS.P",
    "$.WIMPS.R": "remove $.WIMPS.R",
    "$.WIMPS.Pad": "remove $.WIMPS.Pad",
    "$.LIBRARY.view": "remove $.LIBRARY.view",
    "$.WIMPS.Index1": "truncate $.WIMPS.Index1 from 16384 to 4864 bytes",
}
_DISC_SIZE_FIX = "set the disc size from 2560 to 1280 sectors"


def _welcome_copy(tmp_path) -> Path:
    image_filepath = tmp_path / _WELCOME.name
    shutil.copyfile(_WELCOME, image_filepath)
    return image_filepath


def _readable_files(adfs: ADFS) -> dict[str, bytes]:
    files: dict[str, bytes] = {}

    def walk(path) -> None:
        for child in path.iterdir():
            if child.is_dir():
                walk(child)
            else:
                files[child.path] = child.read_bytes()

    walk(adfs.root)
    return files


class TestValidateFindsEveryUnreachableObject:
    def test_each_object_has_a_finding_with_its_fix(self):
        with ADFS.from_file(_WELCOME, read_only=True) as adfs:
            findings = adfs.validate()
        fixes = {str(finding).split(":")[0]: fix_of(finding) for finding in findings}
        disc_size_fix = fixes.pop("Disc size")
        assert disc_size_fix is not None
        assert disc_size_fix.description.startswith(_DISC_SIZE_FIX)
        assert sorted(fixes) == sorted(_WELCOME_FINDINGS)
        for path, fix in fixes.items():
            assert fix is not None, path
            assert fix.description.startswith(_WELCOME_FINDINGS[path]), fix.description

    def test_a_disc_matching_its_image_has_no_size_finding(self):
        adfs = ADFS.from_buffer(memoryview(make_adfs_s_image()))
        assert adfs.validate() == []


class TestRepairingTheWelcomeCapture:
    @pytest.fixture
    def repaired(self, tmp_path) -> tuple[Path, bytes]:
        image_filepath = _welcome_copy(tmp_path)
        before = image_filepath.read_bytes()
        with ADFS.from_file(image_filepath) as adfs:
            for finding in adfs.validate():
                fix_of(finding).apply()
        return image_filepath, before

    def test_leaves_a_disc_validate_passes(self, repaired):
        image_filepath, _ = repaired
        with ADFS.from_file(image_filepath, read_only=True) as adfs:
            assert adfs.validate() == []

    def test_keeps_the_image_size(self, repaired):
        image_filepath, before = repaired
        assert len(image_filepath.read_bytes()) == len(before)

    def test_keeps_every_readable_file(self, repaired):
        image_filepath, _ = repaired
        with ADFS.from_file(_WELCOME, read_only=True) as adfs:
            files = _readable_files_but(adfs, _WELCOME_FINDINGS)
        with ADFS.from_file(image_filepath, read_only=True) as adfs:
            after = _readable_files(adfs)
        index1 = after.pop("$.WIMPS.Index1")
        assert after == files

        # The part of Index1 the image holds: sectors 1261-1279.
        assert index1 == _WELCOME.read_bytes()[1261 * 256 : 1280 * 256]

    def test_describes_the_disc_the_image_holds(self, repaired):
        image_filepath, _ = repaired
        with ADFS.from_file(image_filepath, read_only=True) as adfs:
            assert adfs.total_size == 1280 * 256
            assert all(
                (start + length) // 256 <= 1280 for start, length in adfs._fsm.free_space_entries()
            )


def _readable_files_but(adfs: ADFS, unreachable) -> dict[str, bytes]:
    """Every file of the unrepaired image, skipping those it cannot supply."""
    files: dict[str, bytes] = {}

    def walk(path) -> None:
        for child in path.iterdir():
            if child.path in unreachable:
                continue
            if child.is_dir():
                walk(child)
            else:
                files[child.path] = child.read_bytes()

    walk(adfs.root)
    return files


class TestTrimmedIsNotTruncated:
    """An image short of its disc but holding everything on it is not truncated.

    Hard-disc images, and many floppy images, stop at the last sector in use;
    the rest of the disc is unwritten. That is how such images are stored,
    not a defect, so validate reports nothing and repair leaves the disc
    size alone. Only an image cut short of objects it refers to is truncated.
    """

    def test_a_trimmed_hard_disc_has_no_disc_size_finding(self):
        # BeebEm's scsi1.dat: 94 sectors of a 40264-sector disc, all of it in use.
        with ADFS.from_file(BEEBEM_IMAGES_DIRPATH / "scsi1.dat", read_only=True) as adfs:
            assert not [f for f in adfs.validate() if str(f).startswith("Disc size")]

    def test_a_truncated_floppy_has_a_disc_size_finding(self):
        # BeebEm's armdisc3.adl: 800 sectors of an L disc, with files past the end.
        with ADFS.from_file(BEEBEM_IMAGES_DIRPATH / "armdisc3.adl", read_only=True) as adfs:
            findings = [str(f) for f in adfs.validate()]
        assert "Disc size: the free-space map gives 2560 sectors, but the image holds 800" in (
            findings
        )

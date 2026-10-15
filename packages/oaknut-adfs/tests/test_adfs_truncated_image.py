"""A truncated ADFS image whose directory tree points past its end (#88).

The Master Compact Welcome capture holds only the first 1280 sectors of an
L-format disc, so two of its directories start beyond the image. Walking
the tree must treat such a directory as one it cannot read, as it does a
corrupt one, rather than let the out-of-bounds sector read escape: the walk
runs while identifying the disc, so an escaping error breaks every command.
"""

from __future__ import annotations

import pytest
from helpers.adfs_image import make_adfs_s_image, make_old_dir_entry
from oaknut.adfs import ADFS
from oaknut.adfs.exceptions import ADFSBeyondImageError, ADFSError
from oaknut.filesystem import identify

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

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

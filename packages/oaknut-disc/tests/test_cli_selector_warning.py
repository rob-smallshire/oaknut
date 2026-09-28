"""A partition selector written with a dot instead of a colon warns.

``scsi0.dat:afs.ELITE.MAX`` is a legal ADFS path whose first directory is
named ``afs`` — but on an image that *has* an ``afs`` partition it is
almost certainly a mistyped ``scsi0.dat:afs:ELITE.MAX``. The command still
does what the path says (a directory named ``afs`` is legal); it warns on
stderr and suggests the selector. See issue #52.
"""

from __future__ import annotations

import shutil

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli
from oaknut.disc.mount import misplaced_selector

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"
_L3FS_DSC = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dsc"

_COMBINED = ["adfs", "afs"]


class TestMisplacedSelector:
    def test_dot_after_a_partition_key_is_flagged(self):
        assert misplaced_selector("afs.ELITE.MAX", _COMBINED) == "afs:ELITE.MAX"

    def test_bare_partition_key_is_flagged(self):
        assert misplaced_selector("afs", _COMBINED) == "afs:"

    def test_host_key_is_flagged_too(self):
        assert misplaced_selector("adfs.Games", _COMBINED) == "adfs:Games"

    def test_numbered_selector_is_flagged(self):
        available = ["adfs", "afs", "afs.1"]
        assert misplaced_selector("afs.1.ELITE", available) == "afs.1:ELITE"
        assert misplaced_selector("afs.ELITE", available) == "afs:ELITE"

    @pytest.mark.parametrize(
        "inner_path",
        ["$.afs.ELITE", "afsx.ELITE", "AFS.ELITE", "ELITE.afs", "", "$"],
    )
    def test_other_paths_are_not_flagged(self, inner_path):
        assert misplaced_selector(inner_path, _COMBINED) is None

    def test_single_partition_image_is_not_flagged(self):
        # With only one partition there is nothing to confuse it with.
        assert misplaced_selector("adfs.Games", ["adfs"]) is None


@pytest.fixture
def combined_filepath(tmp_path):
    outer_filepath = tmp_path / "scsi0.dat"
    shutil.copy(_L3FS_DAT, outer_filepath)
    shutil.copy(_L3FS_DSC, tmp_path / "scsi0.dsc")
    return outer_filepath


def _run(*args, input=None):
    return CliRunner().invoke(cli, list(args), input=input)


def test_cp_with_dotted_selector_warns_and_still_copies(combined_filepath, dfs_image_filepath):
    result = _run("cp", f"{dfs_image_filepath}:$.HELLO", f"{combined_filepath}:afs.ELITE.MAX")
    assert result.exit_code == 0, result.output
    assert "did you mean 'afs:ELITE.MAX'" in result.stderr
    # The path is honoured as written: a directory named afs on the ADFS side.
    listing = _run("ls", f"{combined_filepath}:adfs:$.afs.ELITE")
    assert "MAX" in listing.stdout


def test_put_with_dotted_selector_warns_before_failing(combined_filepath):
    # Unlike cp, put does not create the missing "afs" directory, so the
    # command fails — and the warning explains why.
    result = _run("put", f"{combined_filepath}:afs.NOTES", "-", input="hello")
    assert result.exit_code != 0
    assert "did you mean 'afs:NOTES'" in result.stderr


def test_colon_selector_does_not_warn(combined_filepath, dfs_image_filepath):
    result = _run("cp", f"{dfs_image_filepath}:$.HELLO", f"{combined_filepath}:afs:$.MAX")
    assert result.exit_code == 0, result.output
    assert "did you mean" not in result.stderr


def test_single_partition_image_does_not_warn(dfs_image_filepath):
    result = _run("ls", f"{dfs_image_filepath}:$")
    assert "did you mean" not in result.stderr

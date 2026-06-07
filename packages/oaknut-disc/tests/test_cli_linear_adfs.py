"""CLI regression for a linearly-imaged 640K ADFS disc.

The reader's report came in through the `disc` CLI: `identify` called it a
STRONG ADFS disc and `validate` passed, yet `ls` and `tree` failed with a
directory-tail signature of `faul` because the image is laid out in
linear logical-sector order, not the interleaved `.adl` convention. These
tests pin the whole CLI surface they touched against the actual fixture.
"""

from click.testing import CliRunner
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_BCPL = REFERENCE_IMAGES_DIRPATH / "adfs-linear" / "BCPL.adf"


class TestLinearAdfsCli:
    def test_identify_is_strong_adfs(self, runner: CliRunner):
        result = runner.invoke(cli, ["identify", str(_BCPL)])
        assert result.exit_code == 0, result.output
        assert "adfs" in result.output
        assert "STRONG" in result.output

    def test_ls_lists_the_root(self, runner: CliRunner):
        # Previously failed: "Directory tail signature b'faul' ...".
        result = runner.invoke(cli, ["ls", f"{_BCPL}:$"])
        assert result.exit_code == 0, result.output
        for name in ("ALib", "Library", "ReadMe"):
            assert name in result.output

    def test_tree_descends_into_subdirectories(self, runner: CliRunner):
        # Previously failed: "Invalid directory signature ...".
        result = runner.invoke(cli, ["tree", str(_BCPL)])
        assert result.exit_code == 0, result.output
        # $.Library is the directory whose sectors cross a track boundary.
        for name in ("Library", "bcpl", "join"):
            assert name in result.output

    def test_validate_passes(self, runner: CliRunner):
        result = runner.invoke(cli, ["validate", str(_BCPL)])
        assert result.exit_code == 0, result.output

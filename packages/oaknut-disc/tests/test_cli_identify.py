"""CLI tests for `disc identify`, `list-formats`, and `describe-format`."""

from click.testing import CliRunner
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"

_CONFIDENCE_WORDS = ("CERTAIN", "STRONG", "PROBABLE", "POSSIBLE")


class TestIdentify:
    def test_identifies_a_dfs_image(self, runner: CliRunner, dfs_image_filepath):
        result = runner.invoke(cli, ["identify", str(dfs_image_filepath)])
        assert result.exit_code == 0
        assert "acorn_dfs" in result.output
        assert "dfs" in result.output
        assert "PROBABLE" in result.output

    def test_identifies_a_combined_adfs_afs_image(self, runner: CliRunner):
        result = runner.invoke(cli, ["identify", str(_L3FS_DAT)])
        assert result.exit_code == 0
        # Both partitions are reported, AFS (CERTAIN) leading.
        assert "afs" in result.output
        assert "adfs" in result.output
        assert "CERTAIN" in result.output

    def test_content_wins_over_extension(self, runner: CliRunner, dfs_image_filepath, tmp_path):
        # Copy the DFS bytes under a misleading .adf name; identification
        # must still report dfs.
        misnamed = tmp_path / "mystery.adf"
        misnamed.write_bytes(dfs_image_filepath.read_bytes())
        result = runner.invoke(cli, ["identify", str(misnamed)])
        assert result.exit_code == 0
        assert "dfs" in result.output

    def test_unrecognised_image_reports_nothing(self, runner: CliRunner, tmp_path):
        mystery = tmp_path / "mystery.bin"
        mystery.write_bytes(b"this is plainly not any Acorn disc image")
        result = runner.invoke(cli, ["identify", str(mystery)])
        assert result.exit_code == 0
        # No candidate rows: none of the confidence levels appear.
        assert not any(word in result.output for word in _CONFIDENCE_WORDS)

    def test_display_format_renders(self, runner: CliRunner, dfs_image_filepath):
        # The human-facing Rich rendering must not error.
        result = runner.invoke(cli, ["identify", "--as", "display", str(dfs_image_filepath)])
        assert result.exit_code == 0
        assert "acorn_dfs" in result.output

    def test_missing_file_is_a_clean_error(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["identify", str(tmp_path / "nope.ssd")])
        assert result.exit_code != 0


class TestListFormats:
    def test_lists_every_registered_format(self, runner: CliRunner):
        result = runner.invoke(cli, ["list-formats"])
        assert result.exit_code == 0
        for name in ("acorn_dfs", "watford_dfs", "adfs", "afs", "zip"):
            assert name in result.output


class TestDescribeFormat:
    def test_describes_a_known_format(self, runner: CliRunner):
        result = runner.invoke(cli, ["describe-format", "afs"])
        assert result.exit_code == 0
        assert "Level 3 File Server" in result.output

    def test_unknown_format_is_rejected(self, runner: CliRunner):
        result = runner.invoke(cli, ["describe-format", "nonsense"])
        assert result.exit_code != 0

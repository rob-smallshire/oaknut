"""An unrecognised image is explained, not merely reported (#82).

Every installed filesystem says why it declined the image, and both the
"not recognised" error and ``disc identify`` pass those reasons on.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli
from oaknut.filesystem import filesystem_names


def _unrecognisable(tmp_path: Path) -> Path:
    # 200 KiB of a byte no catalogue, map or header accepts.
    image = tmp_path / "mystery.dsd"
    image.write_bytes(b"\xff" * 204800)
    return image


def _reason_lines(output: str) -> dict[str, str]:
    """``  name: reason`` lines from an error, keyed by filesystem name."""
    lines = {}
    for line in output.splitlines():
        stripped = line.strip()
        name, sep, reason = stripped.partition(": ")
        if line.startswith("  ") and sep and name in filesystem_names():
            lines[name] = reason.strip()
    return lines


class TestUnrecognisedError:
    def test_lists_a_line_for_every_installed_filesystem(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["ls", str(_unrecognisable(tmp_path))])
        assert result.exit_code != 0
        assert "no installed filesystem recognises 'mystery.dsd'" in result.output
        assert set(_reason_lines(result.output)) == set(filesystem_names())


class TestIdentifyReportsRejections:
    def test_rejections_report_lists_each_declining_filesystem(self, runner: CliRunner, tmp_path):
        result = runner.invoke(
            cli,
            ["identify", "--report", "rejections", "--as", "tsv", str(_unrecognisable(tmp_path))],
        )
        assert result.exit_code == 0, result.output
        rows = [r.split("\t") for r in result.output.splitlines() if r and not r.startswith("#")]
        assert {row[0] for row in rows} == set(filesystem_names())

    def test_a_recognised_image_still_explains_the_others(
        self, runner: CliRunner, dfs_image_filepath
    ):
        result = runner.invoke(
            cli, ["identify", "--report", "rejections", "--as", "tsv", str(dfs_image_filepath)]
        )
        assert result.exit_code == 0, result.output
        names = {r.split("\t")[0] for r in result.output.splitlines() if r and r[0] != "#"}
        assert "acorn-dfs" not in names
        assert "adfs" in names

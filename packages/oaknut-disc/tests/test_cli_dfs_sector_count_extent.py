"""stat and freemap agree when a DFS catalogue's count and the image differ (#96)."""

from __future__ import annotations

from click.testing import CliRunner
from oaknut.disc.cli import cli


def _trimmed_to_40_tracks(runner: CliRunner, tmp_path):
    """An 80-track DFS disc (catalogue: 800 sectors) cut to its first 40 tracks."""
    image = tmp_path / "side.ssd"
    assert runner.invoke(cli, ["create", str(image), "--title", "T"]).exit_code == 0
    image.write_bytes(image.read_bytes()[: 400 * 256])
    return image


def test_stat_sizes_the_image_and_says_why(runner: CliRunner, tmp_path):
    image = _trimmed_to_40_tracks(runner, tmp_path)
    result = runner.invoke(cli, ["stat", str(image)])
    assert result.exit_code == 0, result.output
    lines = dict(line.split("\t", 1) for line in result.output.splitlines() if "\t" in line)
    assert lines["Size"] == str(400 * 256)
    assert lines["Free"] == str(398 * 256)
    assert "catalogue declares 800 sectors but the image holds 400" in lines["Notes"]


def test_freemap_covers_the_sectors_that_exist(runner: CliRunner, tmp_path):
    image = _trimmed_to_40_tracks(runner, tmp_path)
    result = runner.invoke(cli, ["freemap", str(image)])
    assert result.exit_code == 0, result.output
    assert "Free: 398 of 400 sectors" in result.output


def test_validate_accepts_a_trimmed_image(runner: CliRunner, tmp_path):
    image = _trimmed_to_40_tracks(runner, tmp_path)
    assert runner.invoke(cli, ["validate", str(image)]).exit_code == 0

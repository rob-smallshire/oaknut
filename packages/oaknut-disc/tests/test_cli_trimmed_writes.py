"""Writes to a trimmed image persist (#86).

Many writers stop an image at the last file's last byte. Reading such an
image pads it in memory and never changes the file; writing to it grows
the file to its full disc first, so the change is not lost in the pad.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli

_TRIMMED_BYTES = 150000
_FULL_BYTES = 80 * 10 * 256  # the 80-track single-sided disc a .ssd defaults to


def _trimmed_ssd(runner: CliRunner, tmp_path: Path) -> Path:
    image = tmp_path / "t.ssd"
    assert runner.invoke(cli, ["create", str(image), "--title", "T"]).exit_code == 0
    image.write_bytes(image.read_bytes()[:_TRIMMED_BYTES])
    return image


def test_put_on_a_trimmed_image_persists_and_grows_it(runner, tmp_path):
    image = _trimmed_ssd(runner, tmp_path)
    host = tmp_path / "file"
    host.write_bytes(b"hello")
    result = runner.invoke(cli, ["put", f"{image}:$.NEW", str(host), "--meta-format", "none"])
    assert result.exit_code == 0, result.output
    assert image.stat().st_size == _FULL_BYTES
    assert runner.invoke(cli, ["cat", f"{image}:$.NEW"]).output == "hello"


def test_reading_a_trimmed_image_leaves_it_alone(runner, tmp_path):
    image = _trimmed_ssd(runner, tmp_path)
    assert runner.invoke(cli, ["ls", str(image)]).exit_code == 0
    assert image.stat().st_size == _TRIMMED_BYTES


def test_a_dry_run_leaves_a_trimmed_image_alone(runner, tmp_path):
    image = _trimmed_ssd(runner, tmp_path)
    runner.invoke(cli, ["rm", "--dry-run", f"{image}:$.NONE"])
    assert image.stat().st_size == _TRIMMED_BYTES

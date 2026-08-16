"""Load/exec are shown at the width of the filing system's address field.

DFS keeps 18-bit addresses that MOS ``*INFO`` prints as six hex digits;
ADFS and AFS keep full 32-bit fields that RISC OS ``*Info`` prints as
eight. The display honours that, so a small ADFS address still reads as
the four-byte field it is (and load/exec never differ in width within a
row, as they did before).
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli


def _run(runner, *args, env=None):
    return runner.invoke(cli, list(args), env=env)


class TestAddressWidth:
    def test_dfs_shows_six_hex_digits(self, runner: CliRunner, dfs_image_filepath: Path):
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            f"{dfs_image_filepath}:$", env={"COLUMNS": "200"},
        ).output
        assert "0x001900" in out and "0x008023" in out
        assert "0x00001900" not in out

    def test_adfs_shows_eight_hex_digits(self, runner: CliRunner, adfs_image_filepath: Path):
        # The same 0x1900/0x8023 pair, but ADFS fields are four bytes.
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            f"{adfs_image_filepath}:$", env={"COLUMNS": "200"},
        ).output
        assert "0x00001900" in out and "0x00008023" in out

    def test_stat_adfs_shows_eight_hex_digits(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        out = _run(
            runner, "stat", "--as", "display",
            f"{adfs_image_filepath}:$.Hello", env={"COLUMNS": "200"},
        ).output
        assert "0x00001900" in out and "0x00008023" in out

    def test_get_load_adfs_is_eight_hex_digits(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        out = _run(
            runner, "get-load", "--as", "display", f"{adfs_image_filepath}:$.Hello"
        ).output
        assert "0x00001900" in out

    def test_get_load_dfs_is_six_hex_digits(
        self, runner: CliRunner, dfs_image_filepath: Path
    ):
        out = _run(
            runner, "get-load", "--as", "display", f"{dfs_image_filepath}:$.Hello"
        ).output
        assert "0x001900" in out and "0x00001900" not in out

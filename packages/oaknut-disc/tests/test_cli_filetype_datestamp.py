"""CLI tests for filetype / datestamp display and the get/set verbs."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli


def _run(runner, *args):
    result = runner.invoke(cli, list(args))
    return result


class TestADFSVerbs:
    def test_set_get_filetype_round_trips(self, runner: CliRunner, adfs_image_filepath: Path):
        assert _run(runner, "set-filetype", f"{adfs_image_filepath}:$.Hello", "Text").exit_code == 0
        got = _run(runner, "get-filetype", "--as", "display", f"{adfs_image_filepath}:$.Hello")
        assert got.exit_code == 0, got.output
        assert "Text" in got.output

    def test_set_get_datestamp_round_trips(self, runner: CliRunner, adfs_image_filepath: Path):
        assert (
            _run(
                runner,
                "set-datestamp",
                f"{adfs_image_filepath}:$.Hello",
                "2024-03-01T14:22:08",
            ).exit_code
            == 0
        )
        got = _run(runner, "get-datestamp", "--as", "display", f"{adfs_image_filepath}:$.Hello")
        assert got.exit_code == 0, got.output
        assert "2024-03-01T14:22:08" in got.output

    def test_get_filetype_untyped_file(self, runner: CliRunner, adfs_image_filepath: Path):
        got = _run(runner, "get-filetype", "--as", "display", f"{adfs_image_filepath}:$.Hello")
        assert got.exit_code == 0
        assert "untyped" in got.output


class TestADFSDisplay:
    def _stamp(self, runner, image):
        _run(runner, "set-filetype", f"{image}:$.Hello", "Text")
        _run(runner, "set-datestamp", f"{image}:$.Hello", "2024-03-01T14:22:08")

    def test_ls_shows_type_and_date_and_conceals_addresses(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        self._stamp(runner, adfs_image_filepath)
        out = _run(
            runner, "ls", "--as", "display", "--detailed", f"{adfs_image_filepath}:$"
        ).output
        assert "Text" in out
        assert "2024-03-01T14:22:08" in out
        # The stamped load/exec (0xFFF…) are concealed from the human table.
        assert "0xFFF" not in out

    def test_json_keeps_raw_load_and_numeric_filetype(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        self._stamp(runner, adfs_image_filepath)
        out = _run(
            runner, "ls", "--as", "json", "--detailed", f"{adfs_image_filepath}:$"
        ).output
        rows = json.loads(out)["reports"]["entries"]["rows"]
        hello = next(r for r in rows if r["name"] == "Hello")
        # Machine output stays faithful: raw load int and numeric filetype.
        assert isinstance(hello["load"], int)
        assert hello["load"] & 0xFFF00000 == 0xFFF00000
        assert hello["filetype"] == 0xFFF

    def test_stat_shows_filetype_and_datestamp(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        self._stamp(runner, adfs_image_filepath)
        out = _run(
            runner, "stat", "--as", "display", f"{adfs_image_filepath}:$.Hello"
        ).output
        assert "Text" in out
        assert "2024-03-01T14:22:08" in out


class TestUnsupportedFilesystems:
    def test_dfs_set_filetype_errors_cleanly(self, runner: CliRunner, dfs_image_filepath: Path):
        result = _run(runner, "set-filetype", f"{dfs_image_filepath}:$.Hello", "Text")
        assert result.exit_code != 0
        assert "filetype" in result.output

    def test_dfs_get_datestamp_errors_cleanly(self, runner: CliRunner, dfs_image_filepath: Path):
        result = _run(runner, "get-datestamp", f"{dfs_image_filepath}:$.Hello")
        assert result.exit_code != 0
        assert "datestamp" in result.output


class TestAFS:
    # A linear hard-disc image: its AFS partition is a writable window
    # (an interleaved floppy partition is not).
    def test_set_get_datestamp_date_only(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        image = partitioned_image_with_files
        assert (
            _run(
                runner, "set-datestamp", f"{image}:afs:$.afsA", "2005-06-15T14:30:00"
            ).exit_code
            == 0
        )
        got = _run(runner, "get-datestamp", "--as", "display", f"{image}:afs:$.afsA")
        assert got.exit_code == 0, got.output
        assert "2005-06-15" in got.output
        # Day resolution: the time of day is not part of the rendering.
        assert "14:30" not in got.output

    def test_set_filetype_errors_cleanly(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        result = _run(
            runner, "set-filetype", f"{partitioned_image_with_files}:afs:$.afsA", "Text"
        )
        assert result.exit_code != 0
        assert "filetype" in result.output

    def test_ls_shows_datestamp_and_keeps_addresses(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        image = partitioned_image_with_files
        _run(runner, "set-datestamp", f"{image}:afs:$.afsA", "2005-06-15T14:30:00")
        # Widen the terminal so the load/exec/datestamp columns are not
        # truncated to fit (AFS keeps all three).
        out = runner.invoke(
            cli,
            ["ls", "--as", "display", "--detailed", f"{image}:afs:$"],
            env={"COLUMNS": "240"},
        ).output
        assert "2005-06-15" in out
        # AFS keeps real load/exec addresses; the datestamp is a separate field.
        assert "0x" in out

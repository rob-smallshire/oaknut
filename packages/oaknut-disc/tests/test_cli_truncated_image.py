"""The disc CLI on a truncated ADFS image (#88).

The Master Compact Welcome capture holds only the first half of its disc,
so some of its directories and files lie past the end of the image. Every
command identifies the image first, and identification walks the directory
tree, so a sector read past the end escaped as a ``ValueError`` traceback
from all of them.

Export takes everything the image holds, warns about each object it cannot
reach, and exits with a data error.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from exit_codes import ExitCode
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_WELCOME = REFERENCE_IMAGES_DIRPATH / "adfs-truncated" / "welcome-master-compact.adm"


def _assert_no_leaked_exception(result: Result) -> None:
    exc = result.exception
    assert exc is None or isinstance(exc, SystemExit), (
        f"command leaked {type(exc).__name__}: {exc}; a real shell would print a traceback"
    )


def test_identify_names_adfs(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["identify", str(_WELCOME)])
    _assert_no_leaked_exception(result)
    assert result.exit_code == 0, result.output
    assert "adfs" in result.output


def test_ls_lists_the_root(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["ls", str(_WELCOME)])
    _assert_no_leaked_exception(result)
    assert result.exit_code == 0, result.output
    assert "WELCOME" in result.output


def test_ls_lists_a_readable_subdirectory(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["ls", f"{_WELCOME}:$.ABC"])
    _assert_no_leaked_exception(result)
    assert result.exit_code == 0, result.output
    assert "INTER" in result.output


def test_validate_reports_the_unreachable_directories(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["validate", str(_WELCOME)])
    _assert_no_leaked_exception(result)
    assert result.exit_code == ExitCode.DATA_ERR, result.output
    assert "$.WIMPS.P" in result.output
    assert "$.WIMPS.R" in result.output


class TestExport:
    """Export takes what the image holds and warns about what it does not."""

    #: Objects the image cannot hold, each warned about by its path.
    UNREACHABLE = ("$.WIMPS.P", "$.WIMPS.R", "$.WIMPS.Pad", "$.LIBRARY.view", "$.WIMPS.Index1")

    @pytest.fixture
    def exported(self, runner: CliRunner, tmp_path: Path) -> tuple[Result, Path]:
        out_dirpath = tmp_path / "out"
        result = runner.invoke(
            cli, ["export", str(_WELCOME), str(out_dirpath), "--meta-format", "none"]
        )
        _assert_no_leaked_exception(result)
        return result, out_dirpath

    def test_exits_with_a_data_error(self, exported) -> None:
        result, _ = exported
        assert result.exit_code == ExitCode.DATA_ERR, result.output

    def test_warns_about_each_unreachable_object(self, exported) -> None:
        result, _ = exported
        warnings = [line for line in result.output.splitlines() if line.startswith("warning: ")]
        assert sorted(line.split(":")[1].strip() for line in warnings) == sorted(self.UNREACHABLE)
        assert "5 objects could not be exported" in result.output

    def test_exports_everything_readable(self, exported) -> None:
        _, out_dirpath = exported
        assert (out_dirpath / "ABC" / "INTER").read_bytes().startswith(b"\r")
        assert (out_dirpath / "WIMPS" / "Index1").exists() is False
        # Everything under WELCOME lies within the image.
        assert (out_dirpath / "WELCOME" / "UTILITIES" / "Pstruc").stat().st_size == 3383

    def test_makes_no_host_entry_for_an_unreachable_object(self, exported) -> None:
        _, out_dirpath = exported
        # Every child of $.WIMPS (Index1, P, Pad, R) lies wholly or partly past the end.
        assert list((out_dirpath / "WIMPS").iterdir()) == []


def test_cat_of_a_file_past_the_end_is_a_clean_data_error(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["cat", f"{_WELCOME}:$.LIBRARY.view"])
    _assert_no_leaked_exception(result)
    assert result.exit_code == ExitCode.DATA_ERR, result.output
    assert "past the end of the image" in result.output

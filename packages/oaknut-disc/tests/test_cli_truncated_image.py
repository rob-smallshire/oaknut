"""The disc CLI on a truncated ADFS image (#88).

The Master Compact Welcome capture holds only the first half of its disc,
so some of its directories and files lie past the end of the image. Every
command identifies the image first, and identification walks the directory
tree, so a sector read past the end escaped as a ``ValueError`` traceback
from all of them.

Listing a readable directory and validating are settled here. What ``export``
should do with the objects it cannot reach is not yet decided, so its test
asks only that it does not leak an exception.
"""

from __future__ import annotations

from pathlib import Path

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


def test_export_does_not_leak_an_exception(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(cli, ["export", str(_WELCOME), str(tmp_path / "out")])
    _assert_no_leaked_exception(result)


def test_cat_of_a_file_past_the_end_is_a_clean_data_error(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["cat", f"{_WELCOME}:$.LIBRARY.view"])
    _assert_no_leaked_exception(result)
    assert result.exit_code == ExitCode.DATA_ERR, result.output
    assert "past the end of the image" in result.output

"""Failure-mode tests for the disc CLI.

Every CLI subcommand must convert :class:`FSError` raised by the
library into a clean ``click.ClickException`` with a stable per-category
exit code. Stack traces escaping the CLI mean a bug: either the library
raised something other than an ``FSError`` for what is really a
user-input problem, or the command forgot the ``@handles_fs_errors``
decorator.

Each ``Test*Errors`` class covers one command and walks its realistic
failure modes. The shared :func:`assert_clean_error` helper enforces
three invariants on every result:

1. No ``Traceback`` in the captured output.
2. ``exit_code`` matches the category for that error class.
3. The rendered message contains a recognisable hint.

The exit-code constants live in ``oaknut.disc.errors``; tests reference
them by name so the contract stays visible.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner, Result
from oaknut.disc.cli import cli
from oaknut.disc.errors import (
    EXIT_ALREADY_EXISTS,
    EXIT_DIRECTORY_FULL,
    EXIT_PATH_NOT_FOUND,
)


def assert_clean_error(
    result: Result,
    *,
    exit_code: int,
    message_contains: str | tuple[str, ...] | None = None,
) -> None:
    """Assert ``result`` is a clean CLI error (no uncaught traceback, expected exit code).

    Click's ``CliRunner`` captures any exception that escapes the
    command on ``result.exception`` instead of writing a traceback to
    ``result.output``. So the right "no traceback" signal is that
    ``result.exception`` is either ``None`` or a ``SystemExit`` --
    anything else (``FSError``, ``ValueError``, etc.) means the CLI
    leaked it and would have printed a stack trace under a real shell.

    ``message_contains`` may be a string or a tuple of substrings; the
    match is case-insensitive on each.
    """
    exc = result.exception
    if exc is not None and not isinstance(exc, SystemExit):
        raise AssertionError(
            f"command leaked an uncaught exception "
            f"({type(exc).__name__}: {exc}); a real shell would have "
            f"printed a Python traceback"
        )
    assert result.exit_code == exit_code, (
        f"expected exit code {exit_code}, got {result.exit_code}\n"
        f"output:\n{result.output}"
    )
    if message_contains is not None:
        needles = (
            (message_contains,)
            if isinstance(message_contains, str)
            else message_contains
        )
        lowered = result.output.lower()
        for needle in needles:
            assert needle.lower() in lowered, (
                f"expected message containing {needle!r}, got:\n{result.output}"
            )


# ---------------------------------------------------------------------------
# mkdir
# ---------------------------------------------------------------------------


class TestMkdirErrors:
    def test_directory_full(
        self, runner: CliRunner, adfs_image_full_root: Path
    ) -> None:
        result = runner.invoke(
            cli, ["mkdir", str(adfs_image_full_root), "$.OneMore"]
        )
        assert_clean_error(
            result,
            exit_code=EXIT_DIRECTORY_FULL,
            message_contains=("directory full",),
        )

    def test_already_exists_without_p(
        self, runner: CliRunner, adfs_image_filepath: Path
    ) -> None:
        result = runner.invoke(
            cli, ["mkdir", str(adfs_image_filepath), "$.Games"]
        )
        assert_clean_error(
            result,
            exit_code=EXIT_ALREADY_EXISTS,
            message_contains="already exists",
        )

    def test_already_exists_with_p_is_silent(
        self, runner: CliRunner, adfs_image_filepath: Path
    ) -> None:
        result = runner.invoke(
            cli, ["mkdir", "-p", str(adfs_image_filepath), "$.Games"]
        )
        assert result.exit_code == 0, result.output

    def test_parent_not_found(
        self, runner: CliRunner, adfs_image_filepath: Path
    ) -> None:
        result = runner.invoke(
            cli, ["mkdir", str(adfs_image_filepath), "$.NoSuchDir.Child"]
        )
        assert_clean_error(
            result,
            exit_code=EXIT_PATH_NOT_FOUND,
        )

    def test_dfs_not_supported(
        self, runner: CliRunner, dfs_image_filepath: Path
    ) -> None:
        result = runner.invoke(
            cli, ["mkdir", str(dfs_image_filepath), "$.Whatever"]
        )
        # Already a clean ClickException today; exit_code stays at the
        # Click default (1) because this is a usage-shape error, not an
        # FSError category. Just confirm there's no leaked traceback.
        assert result.exception is None or isinstance(
            result.exception, SystemExit
        ), result.exception
        assert result.exit_code == 1
        assert "not supported for DFS" in result.output

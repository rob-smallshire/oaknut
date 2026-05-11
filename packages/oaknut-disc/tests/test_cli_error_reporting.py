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
    EXIT_LOCKED,
    EXIT_NOT_EMPTY,
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


# ---------------------------------------------------------------------------
# mv
# ---------------------------------------------------------------------------


class TestMvErrors:
    def test_source_not_found(
        self, runner: CliRunner, adfs_image_filepath: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["mv", str(adfs_image_filepath), "$.NoSuch", "$.Renamed"],
        )
        assert_clean_error(
            result,
            exit_code=EXIT_PATH_NOT_FOUND,
            message_contains="not found",
        )

    def test_destination_already_exists(
        self, runner: CliRunner, adfs_image_filepath: Path
    ) -> None:
        # Hello and Games both exist in the root; renaming Hello -> Games
        # collides.
        result = runner.invoke(
            cli,
            ["mv", str(adfs_image_filepath), "$.Hello", "$.Games"],
        )
        assert_clean_error(
            result,
            exit_code=EXIT_ALREADY_EXISTS,
            message_contains="already exists",
        )


# ---------------------------------------------------------------------------
# rm
# ---------------------------------------------------------------------------


class TestRmErrors:
    def test_locked_file_without_force(
        self, runner: CliRunner, adfs_image_locked_file: Path
    ) -> None:
        result = runner.invoke(
            cli, ["rm", str(adfs_image_locked_file), "$.Locked"]
        )
        assert_clean_error(
            result,
            exit_code=EXIT_LOCKED,
            message_contains="locked",
        )

    def test_locked_file_with_force_succeeds(
        self, runner: CliRunner, adfs_image_locked_file: Path
    ) -> None:
        result = runner.invoke(
            cli, ["rm", "-f", str(adfs_image_locked_file), "$.Locked"]
        )
        assert result.exit_code == 0, result.output

    def test_nonempty_dir_without_recursive(
        self,
        runner: CliRunner,
        adfs_image_with_subdir_with_entries: Path,
    ) -> None:
        # Without -r, attempting to delete a directory should fail with
        # a clear "is a directory" message and exit 1 (usage error, not
        # an FSError category).
        result = runner.invoke(
            cli,
            ["rm", str(adfs_image_with_subdir_with_entries), "$.Games"],
        )
        assert result.exception is None or isinstance(
            result.exception, SystemExit
        )
        assert result.exit_code == 1
        assert "directory" in result.output.lower()


# ---------------------------------------------------------------------------
# cp
# ---------------------------------------------------------------------------


class TestCpErrors:
    def test_destination_directory_full(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        adfs_image_full_root: Path,
    ) -> None:
        # Copy a single file from a normal image into a target whose
        # root directory is already at the 47-entry maximum.
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{adfs_image_filepath}:$.Hello",
                f"{adfs_image_full_root}:$.Hello",
            ],
        )
        assert_clean_error(
            result,
            exit_code=EXIT_DIRECTORY_FULL,
            message_contains=("directory full",),
        )

    def test_source_not_found(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{adfs_image_filepath}:$.Nope",
                f"{adfs_empty_filepath}:$.Nope",
            ],
        )
        # "no matches" / "path not found" — should be a clean error
        # without a traceback.
        assert result.exception is None or isinstance(
            result.exception, SystemExit
        ), result.exception
        assert result.exit_code != 0

    def test_dfs_catalogue_full(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        dfs_image_full_catalogue: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{adfs_image_filepath}:$.Hello",
                f"{dfs_image_full_catalogue}:$.Hello",
            ],
        )
        assert_clean_error(
            result,
            exit_code=EXIT_DIRECTORY_FULL,
            message_contains=("full",),
        )


# ---------------------------------------------------------------------------
# get / put
# ---------------------------------------------------------------------------


class TestGetErrors:
    def test_path_not_found(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "get",
                str(adfs_image_filepath),
                "$.NoSuch",
                str(tmp_path / "out"),
            ],
        )
        assert_clean_error(
            result,
            exit_code=EXIT_PATH_NOT_FOUND,
            message_contains="not found",
        )

    def test_path_is_directory(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        tmp_path: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "get",
                str(adfs_image_filepath),
                "$.Games",
                str(tmp_path / "out"),
            ],
        )
        assert_clean_error(
            result,
            exit_code=EXIT_PATH_NOT_FOUND,
            message_contains="directory",
        )


class TestPutErrors:
    def test_destination_directory_full(
        self,
        runner: CliRunner,
        adfs_image_full_root: Path,
        tmp_path: Path,
    ) -> None:
        host_filepath = tmp_path / "extra"
        host_filepath.write_bytes(b"more data")
        result = runner.invoke(
            cli,
            [
                "put",
                str(adfs_image_full_root),
                "$.OneMore",
                str(host_filepath),
            ],
        )
        assert_clean_error(
            result,
            exit_code=EXIT_DIRECTORY_FULL,
            message_contains=("directory full",),
        )


# ---------------------------------------------------------------------------
# import / export
# ---------------------------------------------------------------------------


class TestImportErrors:
    def test_import_fills_directory(
        self,
        runner: CliRunner,
        adfs_image_full_root: Path,
        tmp_path: Path,
    ) -> None:
        # A host directory holding one extra file; the target already
        # has 47 entries, so the very first imported file must trip the
        # directory-full check.
        src_dirpath = tmp_path / "src"
        src_dirpath.mkdir()
        (src_dirpath / "Extra").write_bytes(b"x")
        result = runner.invoke(
            cli,
            [
                "import",
                "--meta-format",
                "none",
                str(adfs_image_full_root),
                str(src_dirpath),
            ],
        )
        assert_clean_error(
            result,
            exit_code=EXIT_DIRECTORY_FULL,
            message_contains=("directory full",),
        )


class TestExportErrors:
    """Bulk export is largely read-only and most failure modes are host-side.

    The realistic on-image failure mode is a malformed image, which is
    covered by validate's failure tests. Here we just confirm export
    succeeds on a good image and produces no traceback when the source
    has a directory that happens to be empty.
    """

    def test_export_empty_image_succeeds(
        self,
        runner: CliRunner,
        adfs_empty_filepath: Path,
        tmp_path: Path,
    ) -> None:
        out_dirpath = tmp_path / "out"
        result = runner.invoke(
            cli, ["export", str(adfs_empty_filepath), str(out_dirpath)]
        )
        assert result.exit_code == 0, result.output
        assert out_dirpath.exists()

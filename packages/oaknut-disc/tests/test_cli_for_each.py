"""CLI tests for `disc for-each` — Stage 1: content mode + Reports table.

The headline use case: pipe each matching file's bytes through an
external command and capture the result as a path/output Reports table
(default TSV when stdout is captured). The per-file command in these
tests is a tiny Python invocation rather than ``md5sum`` so the suite
is portable across macOS and Linux without depending on GNU coreutils.
"""

from __future__ import annotations

import sys
from pathlib import Path

from click.testing import CliRunner
from oaknut.dfs import DFS
from oaknut.disc.cli import cli

# A portable per-file command: read stdin, print its byte length. Stands
# in for `md5sum` — same shape (bytes-on-stdin, line-of-text-on-stdout),
# without needing coreutils on every test host.
_BYTELEN = [
    sys.executable,
    "-c",
    "import sys; sys.stdout.write(str(len(sys.stdin.buffer.read())))",
]


def _build_disc(tmp_path: Path) -> Path:
    """A small DFS with three files of known sizes, for predictable per-file output."""
    img = tmp_path / "demo.ssd"
    with DFS.create_file(img, title="Demo") as dfs:
        (dfs.root / "$.A").write_bytes(b"a")
        (dfs.root / "$.BB").write_bytes(b"bb")
        (dfs.root / "$.CCC").write_bytes(b"ccc")
    return img


def _tsv_rows(output: str) -> dict[str, str]:
    """Parse a CliRunner-captured TSV into a {path: output} dict."""
    rows = [
        line for line in output.strip().splitlines() if line and not line.startswith("#")
    ]
    return dict(line.split("\t", 1) for line in rows)


class TestContentMode:
    def test_pipes_each_file_through_command(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        img = _build_disc(tmp_path)
        result = runner.invoke(cli, ["for-each", f"{img}:*", "--", *_BYTELEN])
        assert result.exit_code == 0, result.output
        rows = _tsv_rows(result.output)
        assert rows == {"$.A": "1", "$.BB": "2", "$.CCC": "3"}

    def test_tsv_header_has_path_and_output(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        img = _build_disc(tmp_path)
        result = runner.invoke(cli, ["for-each", f"{img}:*", "--", *_BYTELEN])
        assert result.exit_code == 0
        header = result.output.splitlines()[0]
        assert "path" in header.lower()
        assert "output" in header.lower()

    def test_recursive_by_default_walks_subdirectories(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        # DFS has nominal subdirectories: the populated directory letters
        # ($, A, …) are children of the nameless root. A '*' pattern at
        # the image root must reach every file across them — not just one
        # directory letter — for the recursive-by-default contract.
        img = tmp_path / "split.ssd"
        with DFS.create_file(img, title="Split") as dfs:
            (dfs.root / "$.A").write_bytes(b"a")
            (dfs.root / "B.B").write_bytes(b"bb")
        result = runner.invoke(cli, ["for-each", f"{img}:*", "--", *_BYTELEN])
        assert result.exit_code == 0, result.output
        rows = _tsv_rows(result.output)
        assert rows == {"$.A": "1", "B.B": "2"}

    def test_directories_are_skipped_by_default(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        # On DFS the directory letters are dir entries; for-each must not
        # try to pipe their (non-existent) content into the command.
        img = _build_disc(tmp_path)
        result = runner.invoke(cli, ["for-each", f"{img}:*", "--", *_BYTELEN])
        assert result.exit_code == 0, result.output
        rows = _tsv_rows(result.output)
        # No '$' or other directory-letter entries in the rows.
        for path in rows:
            assert "." in path, f"unexpected directory in results: {path}"

    def test_no_matches_exits_zero_with_empty_table(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        img = _build_disc(tmp_path)
        result = runner.invoke(cli, ["for-each", f"{img}:NOSUCH", "--", *_BYTELEN])
        assert result.exit_code == 0
        # No data rows; header may or may not be present depending on the
        # output format, but no actual matches should appear.
        rows = _tsv_rows(result.output)
        assert rows == {}

    def test_pattern_is_required(self, runner: CliRunner, tmp_path: Path) -> None:
        img = _build_disc(tmp_path)
        # Bare image with no pattern: this command's iteration needs a
        # pattern (matches `find`'s behaviour, not `ls`'s default-root).
        result = runner.invoke(cli, ["for-each", str(img), "--", *_BYTELEN])
        assert result.exit_code != 0

    def test_command_is_required(self, runner: CliRunner, tmp_path: Path) -> None:
        img = _build_disc(tmp_path)
        result = runner.invoke(cli, ["for-each", f"{img}:*"])
        assert result.exit_code != 0


# Echo-argv: a portable command that prints its sole argument verbatim.
# Stands in for any command that consumes a substituted {} value.
_ECHO_ARGV = [
    sys.executable,
    "-c",
    "import sys; sys.stdout.write(sys.argv[1])",
]


class TestPathSpecMode:
    """``--mode path-spec``: the in-image path is substituted, no host file."""

    def test_substitutes_brace(self, runner: CliRunner, tmp_path: Path) -> None:
        img = _build_disc(tmp_path)
        result = runner.invoke(
            cli, ["for-each", f"{img}:*", "--mode", "path-spec", "--", *_ECHO_ARGV, "{}"]
        )
        assert result.exit_code == 0, result.output
        rows = _tsv_rows(result.output)
        assert rows == {"$.A": "$.A", "$.BB": "$.BB", "$.CCC": "$.CCC"}

    def test_appends_when_no_brace(self, runner: CliRunner, tmp_path: Path) -> None:
        img = _build_disc(tmp_path)
        result = runner.invoke(
            cli, ["for-each", f"{img}:*", "--mode", "path-spec", "--", *_ECHO_ARGV]
        )
        assert result.exit_code == 0, result.output
        rows = _tsv_rows(result.output)
        assert rows == {"$.A": "$.A", "$.BB": "$.BB", "$.CCC": "$.CCC"}


class TestFileSpecMode:
    """``--mode file-spec``: full IMAGE:PATH per match — chains with `disc` itself."""

    def test_substitutes_brace_with_full_spec(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        img = _build_disc(tmp_path)
        result = runner.invoke(
            cli, ["for-each", f"{img}:*", "--mode", "file-spec", "--", *_ECHO_ARGV, "{}"]
        )
        assert result.exit_code == 0, result.output
        rows = _tsv_rows(result.output)
        assert rows == {
            "$.A": f"{img}:$.A",
            "$.BB": f"{img}:$.BB",
            "$.CCC": f"{img}:$.CCC",
        }

    def test_composes_with_disc_cat(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        # The headline composition: every match fed through `disc cat` via
        # its FILE_SPEC. The output column is each file's content.
        img = _build_disc(tmp_path)
        result = runner.invoke(
            cli,
            [
                "for-each", f"{img}:*", "--mode", "file-spec",
                "--", "disc", "cat", "{}",
            ],
        )
        assert result.exit_code == 0, result.output
        rows = _tsv_rows(result.output)
        assert rows == {"$.A": "a", "$.BB": "bb", "$.CCC": "ccc"}


class TestTempFileMode:
    """``--mode temp-file``: file materialised to a host temp path."""

    def test_substitutes_brace_with_temp_path_holding_content(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        # cat reads the materialised file; we get the bytes back.
        img = _build_disc(tmp_path)
        result = runner.invoke(
            cli, ["for-each", f"{img}:*", "--mode", "temp-file", "--", "cat", "{}"]
        )
        assert result.exit_code == 0, result.output
        rows = _tsv_rows(result.output)
        assert rows == {"$.A": "a", "$.BB": "bb", "$.CCC": "ccc"}

    def test_temp_files_are_cleaned_up_after_run(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        img = _build_disc(tmp_path)
        result = runner.invoke(
            cli, ["for-each", f"{img}:*", "--mode", "temp-file", "--", *_ECHO_ARGV, "{}"]
        )
        assert result.exit_code == 0, result.output
        rows = _tsv_rows(result.output)
        for temp_path in rows.values():
            assert not Path(temp_path).exists(), f"temp file leaked: {temp_path}"

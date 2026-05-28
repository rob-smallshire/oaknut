"""CLI tests for `disc materialise` — single-file host-tempfile materialisation.

`materialise` is the single-file primitive that ``for-each --mode temp-file``
sugar-coats: write the in-image file to a host temp file, substitute ``{}``
in the command's args with that path (or append it if there is no ``{}``),
run the command, then remove the temp file. The command's stdout / stderr
pass through to the user; its exit code propagates as the disc command's
exit code.
"""

from __future__ import annotations

import sys
from pathlib import Path

from click.testing import CliRunner
from oaknut.dfs import DFS
from oaknut.disc.cli import cli


def _make_disc(tmp_path: Path) -> Path:
    img = tmp_path / "demo.ssd"
    with DFS.create_file(img, title="Demo") as dfs:
        (dfs.root / "$.HELLO").write_bytes(b"hi there")
    return img


# Echo-argv: prints its sole argument verbatim. Used to capture the
# substituted temp-file path so the cleanup test can verify it.
_ECHO_ARGV = [
    sys.executable,
    "-c",
    "import sys; sys.stdout.write(sys.argv[1])",
]


class TestMaterialise:
    def test_substitutes_brace_with_temp_path(
        self, runner: CliRunner, tmp_path: Path, capfd
    ) -> None:
        # materialise spawns a subprocess whose stdout passes through to
        # fd 1 (not into CliRunner's in-process stdout buffer); capfd is
        # what reads it back in tests.
        img = _make_disc(tmp_path)
        result = runner.invoke(
            cli, ["materialise", f"{img}:$.HELLO", "--", "cat", "{}"]
        )
        out, _ = capfd.readouterr()
        assert result.exit_code == 0
        assert out.strip() == "hi there"

    def test_appends_path_when_no_brace(
        self, runner: CliRunner, tmp_path: Path, capfd
    ) -> None:
        img = _make_disc(tmp_path)
        result = runner.invoke(
            cli, ["materialise", f"{img}:$.HELLO", "--", "cat"]
        )
        out, _ = capfd.readouterr()
        assert result.exit_code == 0
        assert out.strip() == "hi there"

    def test_temp_file_is_cleaned_up_after(
        self, runner: CliRunner, tmp_path: Path, capfd
    ) -> None:
        img = _make_disc(tmp_path)
        result = runner.invoke(
            cli, ["materialise", f"{img}:$.HELLO", "--", *_ECHO_ARGV, "{}"]
        )
        out, _ = capfd.readouterr()
        assert result.exit_code == 0
        temp_path = out.strip()
        assert temp_path, "echo subprocess emitted no path"
        assert not Path(temp_path).exists(), f"temp file leaked: {temp_path}"

    def test_propagates_command_exit_code(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        img = _make_disc(tmp_path)
        # A command that exits 7 unconditionally; the disc command's exit
        # code follows.
        result = runner.invoke(
            cli,
            [
                "materialise", f"{img}:$.HELLO",
                "--", sys.executable, "-c", "import sys; sys.exit(7)",
            ],
        )
        assert result.exit_code == 7

    def test_command_is_required(self, runner: CliRunner, tmp_path: Path) -> None:
        img = _make_disc(tmp_path)
        result = runner.invoke(cli, ["materialise", f"{img}:$.HELLO"])
        assert result.exit_code != 0

    def test_file_spec_required(self, runner: CliRunner, tmp_path: Path) -> None:
        img = _make_disc(tmp_path)
        # bare image, no PATH_SPEC — materialise needs to address a file.
        result = runner.invoke(cli, ["materialise", str(img), "--", "cat"])
        assert result.exit_code != 0

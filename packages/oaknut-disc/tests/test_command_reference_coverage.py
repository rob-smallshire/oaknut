"""Coverage guard for the CLI command reference.

Every command registered on the ``disc`` group must appear in
``docs/disc/cli/commands/index.rst`` as an ``.. oaknut-command::``
entry, and every documented command must carry at least one
``.. cli-example::`` whose recipe script exists under
``scripts/cli-examples/``. The reverse direction is checked too: the
reference must not document a command that no longer exists.

This is what catches a newly-added subcommand (or a renamed/removed
one) slipping through without docs — the gap that previously let
``afs-passwd`` ship undocumented.

Star-aliases (Acorn ``*`` command names) are not primary commands and
are excluded. There are no per-command exclusions: a deliberately
"meta" command still has to be documented, just under its own section.
"""

from __future__ import annotations

import re
from pathlib import Path

from oaknut.disc.cli import cli

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REFERENCE_FILEPATH = _REPO_ROOT / "docs" / "disc" / "cli" / "commands" / "index.rst"
_EXAMPLES_DIRPATH = _REPO_ROOT / "scripts" / "cli-examples"

_OAKNUT_COMMAND_RE = re.compile(
    r"^\.\. oaknut-command:: oaknut\.disc\.cli:(\S+)\s*$", re.MULTILINE
)
_CLI_EXAMPLE_RE = re.compile(r"cli-example:: (\S+)")


def _documented_commands() -> dict[str, list[str]]:
    """Map each documented command to the cli-example scripts in its block.

    A command's "block" runs from its ``.. oaknut-command::`` line up to
    the next one (or end of file), which is where its ``:prog:`` line,
    prose, and ``.. cli-example::`` directives live.
    """
    text = _REFERENCE_FILEPATH.read_text()
    matches = list(_OAKNUT_COMMAND_RE.finditer(text))
    documented: dict[str, list[str]] = {}
    for index, match in enumerate(matches):
        name = match.group(1)
        block_start = match.end()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        documented[name] = _CLI_EXAMPLE_RE.findall(text[block_start:block_end])
    return documented


def _cli_command_names() -> set[str]:
    """Primary ``disc`` subcommands (excluding Acorn ``*`` star-aliases)."""
    return {name for name in cli.commands if not name.startswith("*")}


class TestCommandReferenceCoverage:
    def test_reference_file_present(self) -> None:
        assert _REFERENCE_FILEPATH.is_file(), (
            f"command reference not found at {_REFERENCE_FILEPATH}"
        )

    def test_every_command_is_documented(self) -> None:
        undocumented = sorted(_cli_command_names() - set(_documented_commands()))
        assert not undocumented, (
            "CLI commands missing an .. oaknut-command:: entry in "
            f"{_REFERENCE_FILEPATH.name}: {undocumented}"
        )

    def test_no_stale_documented_command(self) -> None:
        stale = sorted(set(_documented_commands()) - _cli_command_names())
        assert not stale, (
            f"{_REFERENCE_FILEPATH.name} documents commands that no longer "
            f"exist on the CLI: {stale}"
        )

    def test_every_documented_command_has_an_example(self) -> None:
        without_example = sorted(
            name for name, examples in _documented_commands().items() if not examples
        )
        assert not without_example, (
            "documented commands with no .. cli-example:: directive: "
            f"{without_example}"
        )

    def test_referenced_example_scripts_exist(self) -> None:
        missing: list[str] = []
        for name, examples in _documented_commands().items():
            for example in examples:
                if not (_EXAMPLES_DIRPATH / f"{example}.py").is_file():
                    missing.append(f"{name} -> {example}.py")
        assert not missing, (
            f"cli-example scripts referenced but absent from {_EXAMPLES_DIRPATH}: "
            f"{missing}"
        )

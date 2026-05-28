"""Tests for the terminal-friendly help machinery."""

import click
from click.testing import CliRunner
from oaknut.cli import PlainHelpFormatter, strip_rst, use_plain_help


class TestStripRst:
    def test_double_backticks_become_plain(self):
        assert strip_rst("pass ``--geometry`` to set it") == "pass --geometry to set it"

    def test_single_backticks_become_plain(self):
        assert strip_rst("run `disc list-filesystems`") == "run disc list-filesystems"

    def test_text_without_markup_is_unchanged(self):
        assert strip_rst("plain text, nothing to do") == "plain text, nothing to do"


class TestUsePlainHelp:
    def _cli(self):
        @click.group()
        def root():
            """Root group with ``markup`` in its help."""

        @root.command()
        @click.option("--thing", help="A thing; see `other-command`.")
        def sub(thing):
            """Do a ``thing`` to the disc."""

        return root

    def test_help_text_is_stripped(self):
        root = self._cli()
        use_plain_help(root)
        result = CliRunner().invoke(root, ["sub", "--help"])
        assert result.exit_code == 0
        assert "`" not in result.output
        # Content survives, only the markup is gone.
        assert "Do a thing to the disc." in result.output
        assert "see other-command." in result.output

    def test_applies_to_the_whole_subtree(self):
        root = self._cli()
        use_plain_help(root)
        # Both the group's own help and the subcommand's use the formatter.
        assert root.context_class.formatter_class is PlainHelpFormatter
        assert root.commands["sub"].context_class.formatter_class is PlainHelpFormatter

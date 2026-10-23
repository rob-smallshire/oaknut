"""Tests for the --meta-format choice type."""

import click
from click.testing import CliRunner
from oaknut.cli import MetaFormatChoice
from oaknut.file import MetaFormat


def _cli():
    @click.command()
    @click.option("--meta-format", type=MetaFormatChoice(), default="inf-trad")
    def show(meta_format):
        click.echo(meta_format)

    return show


class TestMetaFormatChoice:
    def test_choices_are_every_format_and_none(self):
        assert list(MetaFormatChoice().choices) == [*(f.value for f in MetaFormat), "none"]

    def test_deprecated_names_are_not_listed(self):
        assert "filename-mos" not in MetaFormatChoice().choices

    def test_accepts_a_current_name(self):
        result = CliRunner().invoke(_cli(), ["--meta-format", "filename-loadexec"])
        assert result.exit_code == 0
        assert result.stdout == "filename-loadexec\n"

    def test_accepts_none(self):
        result = CliRunner().invoke(_cli(), ["--meta-format", "none"])
        assert result.exit_code == 0
        assert result.stdout == "none\n"

    def test_is_case_insensitive(self):
        result = CliRunner().invoke(_cli(), ["--meta-format", "INF-PIEB"])
        assert result.exit_code == 0
        assert result.stdout == "inf-pieb\n"

    def test_deprecated_name_resolves_and_warns(self):
        result = CliRunner().invoke(_cli(), ["--meta-format", "filename-mos"])
        assert result.exit_code == 0
        assert result.stdout == "filename-loadexec\n"
        assert "deprecated" in result.stderr
        assert "filename-loadexec" in result.stderr

    def test_rejects_an_unknown_name(self):
        result = CliRunner().invoke(_cli(), ["--meta-format", "filename-nfs"])
        assert result.exit_code == 2

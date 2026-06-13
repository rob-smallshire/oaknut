"""Tests for the ``oaknut-basic`` command-line interface.

The CLI is a thin wrapper around the :func:`oaknut.basic.number_lines`
facade. These tests cover the stream plumbing it adds — stdin/stdout
pipe usage, file-to-file usage, the option parsing, and the
byte/text (Acorn-encoding) boundary — rather than re-testing the
numbering logic itself.
"""

from pathlib import Path

from click.testing import CliRunner
from oaknut.basic.cli import cli

_DATA_DIRPATH = Path(__file__).parent / "data"


class TestNumberCommandPipe:
    def test_reads_stdin_writes_stdout(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["number"], input="PRINT\nEND\n")
        assert result.exit_code == 0
        # Default encoding is UTF-8, host-native LF line terminators.
        assert result.stdout_bytes == b"10 PRINT\n20 END\n"

    def test_explicit_dashes_select_stdin_and_stdout(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["number", "-", "-"], input="A\nB")
        assert result.exit_code == 0
        assert result.stdout_bytes == b"10 A\n20 B"

    def test_step_option(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["number", "--step", "1"], input="A\nB\nC")
        assert result.exit_code == 0
        assert result.stdout_bytes == b"10 A\n11 B\n12 C"

    def test_start_option(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["number", "--start", "100"], input="A\nB")
        assert result.exit_code == 0
        assert result.stdout_bytes == b"100 A\n110 B"

    def test_step_below_one_is_rejected_by_click(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["number", "--step", "0"], input="A")
        assert result.exit_code != 0


class TestNumberCommandEncoding:
    def test_acorn_encoding_uses_cr_terminators(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["number", "--encoding", "acorn"], input="PRINT\nEND\n")
        assert result.exit_code == 0
        # Acorn-native text: CR line terminators, ready for disc put.
        assert result.stdout_bytes == b"10 PRINT\r20 END\r"

    def test_acorn_encoding_normalises_the_bbc_pound_sign(self):
        runner = CliRunner()
        # 0xA3 is the pound sign in the BBC character set; the acorn codec
        # decodes it to "£" and re-encodes to the canonical 0x60. The byte
        # is not valid UTF-8, so this genuinely exercises the codec.
        result = runner.invoke(cli, ["number", "--encoding", "acorn"], input=b"PRINT \xa3")
        assert result.exit_code == 0
        assert result.stdout_bytes == b"10 PRINT \x60"

    def test_unknown_encoding_is_a_usage_error(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["number", "--encoding", "klingon"], input="A")
        assert result.exit_code != 0
        assert "encoding" in result.output.lower()


class TestNumberCommandFiles:
    def test_file_to_file_utf8(self, tmp_path: Path):
        input_filepath = tmp_path / "menu.bas"
        output_filepath = tmp_path / "menu-numbered.bas"
        input_filepath.write_text("PRINT\nEND\n")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["number", str(input_filepath), str(output_filepath)],
        )
        assert result.exit_code == 0
        assert output_filepath.read_bytes() == b"10 PRINT\n20 END\n"

    def test_file_to_file_acorn(self, tmp_path: Path):
        # An Acorn-native source: CR terminators in the BBC character set.
        input_filepath = tmp_path / "menu.bas"
        output_filepath = tmp_path / "menu-numbered.bas"
        input_filepath.write_bytes(b"PRINT\rEND")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["number", "--encoding", "acorn", str(input_filepath), str(output_filepath)],
        )
        assert result.exit_code == 0
        assert output_filepath.read_bytes() == b"10 PRINT\r20 END"

    def test_file_to_stdout(self, tmp_path: Path):
        input_filepath = tmp_path / "menu.bas"
        input_filepath.write_text("PRINT\nEND")

        runner = CliRunner()
        result = runner.invoke(cli, ["number", str(input_filepath)])
        assert result.exit_code == 0
        assert result.stdout_bytes == b"10 PRINT\n20 END"

    def test_missing_input_file_is_a_usage_error(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(cli, ["number", str(tmp_path / "absent.bas")])
        assert result.exit_code != 0

    def test_numbers_a_real_program_end_to_end(self):
        # ragged.bas is unnumbered source whose GOTO targets assume
        # AUTO 10,10; the default numbering must reproduce them so the
        # emitted program still runs.
        runner = CliRunner()
        result = runner.invoke(cli, ["number", str(_DATA_DIRPATH / "ragged.bas")])
        assert result.exit_code == 0
        # Default UTF-8 / LF, first line numbered 10, and a hand-written
        # GOTO target landing exactly where it should.
        assert result.stdout_bytes.startswith(b"10 REM ===")
        assert b"\n740 REM space between lines\n" in result.stdout_bytes


class TestTopLevel:
    def test_version_option(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "oaknut-basic" in result.output

    def test_help_lists_number_command(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "number" in result.output

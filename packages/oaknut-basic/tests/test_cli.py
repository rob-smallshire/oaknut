"""Tests for the ``oaknut-basic`` command-line interface.

The CLI is a thin wrapper around the library facades. These tests cover
the stream plumbing it adds — stdin/stdout pipe usage, file-to-file
usage, the option parsing, and the byte/text (Acorn-encoding) boundary —
rather than re-testing the numbering or tokenising logic itself.
"""

from pathlib import Path

import oaknut.basic as basic
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


class TestTokeniseCommand:
    def test_pipe_tokenises_to_stdout(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["tokenise"], input=b"10 PRINT\n")
        assert result.exit_code == 0
        assert result.stdout_bytes == basic.tokenise("10 PRINT\n")

    def test_file_to_file(self, tmp_path: Path):
        source_filepath = tmp_path / "prog.bas"
        output_filepath = tmp_path / "PROG"
        source_filepath.write_bytes(b"10 PRINT\n20 END\n")
        runner = CliRunner()
        result = runner.invoke(cli, ["tokenise", str(source_filepath), str(output_filepath)])
        assert result.exit_code == 0
        assert output_filepath.read_bytes() == basic.tokenise("10 PRINT\n20 END\n")

    def test_auto_number(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["tokenise", "--start", "10"], input=b"PRINT\nEND\n")
        assert result.exit_code == 0
        assert result.stdout_bytes == basic.tokenise("PRINT\nEND\n", start=10)

    def test_already_numbered_under_auto_errors_with_a_note(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["tokenise", "--start", "10"], input=b"10 PRINT\n")
        assert result.exit_code != 0
        assert "already numbered" in result.output
        assert "Drop --start/--step" in result.output  # the actionable note

    def test_unnumbered_without_auto_errors(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["tokenise"], input=b"PRINT\n")
        assert result.exit_code != 0
        assert "no line number" in result.output


class TestTokeniseEncoding:
    def test_default_decodes_host_utf8_pound_sign(self):
        # The default encoding is UTF-8, so a £ typed in a host editor
        # (0xC2 0xA3) maps to the single Acorn code point, not the raw
        # multibyte sequence.
        runner = CliRunner()
        result = runner.invoke(cli, ["tokenise"], input='10 PRINT "£"\n'.encode("utf-8"))
        assert result.exit_code == 0
        # Acorn stores £ as 0x60 inside the tokenised string literal.
        assert b'"\x60"' in result.stdout_bytes

    def test_acorn_encoding_passes_raw_bytes_through(self):
        # --encoding acorn treats the input as Acorn bytes already, so a
        # 0x60 byte is the £ literal verbatim.
        runner = CliRunner()
        result = runner.invoke(
            cli, ["tokenise", "--encoding", "acorn"], input=b'10 PRINT "\x60"\n'
        )
        assert result.exit_code == 0
        assert b'"\x60"' in result.stdout_bytes


class TestDetokeniseCommand:
    def test_pipe_detokenises_to_stdout(self):
        program = basic.tokenise("10 PRINT")
        runner = CliRunner()
        result = runner.invoke(cli, ["detokenise"], input=program)
        assert result.exit_code == 0
        # Default UTF-8 output: host-native LF line ending.
        assert result.stdout_bytes == b"10 PRINT\n"

    def test_acorn_encoding_uses_cr_terminators(self):
        program = basic.tokenise("10 PRINT")
        runner = CliRunner()
        result = runner.invoke(cli, ["detokenise", "--encoding", "acorn"], input=program)
        assert result.exit_code == 0
        # Acorn output: native CR line ending.
        assert result.stdout_bytes == b"10 PRINT\r"

    def test_default_writes_host_utf8_pound_sign(self):
        # A program whose string literal holds the Acorn £ (0x60)
        # de-tokenises to a UTF-8 £ under the default encoding.
        program = basic.tokenise('10 PRINT "£"')
        runner = CliRunner()
        result = runner.invoke(cli, ["detokenise"], input=program)
        assert result.exit_code == 0
        assert "£".encode("utf-8") in result.stdout_bytes

    def test_malformed_program_reports_the_offset(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["detokenise"], input=b"\x99")
        assert result.exit_code != 0
        assert "offset 0" in result.output

    def test_dialect_v_decodes_escape_tokens(self):
        # &C8 &91 is the BASIC V ORIGIN statement, not "LOADTIME".
        program = b"\x0d\x00\x8c\x0e\xc8\x91 640,512\x0d\xff"
        runner = CliRunner()
        result = runner.invoke(cli, ["detokenise", "--dialect", "v"], input=program)
        assert result.exit_code == 0
        assert result.stdout_bytes == b"140ORIGIN 640,512\n"

    def test_default_dialect_is_basic_ii(self):
        program = b"\x0d\x00\x8c\x0e\xc8\x91 640,512\x0d\xff"
        runner = CliRunner()
        result = runner.invoke(cli, ["detokenise"], input=program)
        assert result.exit_code == 0
        assert result.stdout_bytes == b"140LOADTIME 640,512\n"


class TestTokeniseDetokeniseRoundTrip:
    def test_cli_round_trip(self):
        runner = CliRunner()
        tokenised = runner.invoke(cli, ["tokenise"], input=b"10 PRINT\n20 GOTO 10\n")
        assert tokenised.exit_code == 0
        listing = runner.invoke(cli, ["detokenise"], input=tokenised.stdout_bytes)
        assert listing.exit_code == 0
        # Default UTF-8 output: host-native LF line endings.
        assert listing.stdout_bytes == b"10 PRINT\n20 GOTO 10\n"

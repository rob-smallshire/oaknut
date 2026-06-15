"""Tests for the BBC BASIC II de-tokeniser.

Inputs are hand-built token streams so each rule is exercised in
isolation: the line framing, keyword expansion, &8D references, quoted
strings (including token-valued bytes that must stay literal), and the
malformed-input guards.
"""

import pytest
from oaknut.basic.detokeniser import detokenise
from oaknut.basic.exceptions import (
    DetokeniseError,
    InvalidLineLengthError,
    MissingLineMarkerError,
    TruncatedProgramError,
)


def _program(*lines: tuple[int, bytes]) -> bytes:
    """Frame (line_number, body) pairs into a tokenised program."""
    out = bytearray()
    for line_number, body in lines:
        out += bytes((0x0D, (line_number >> 8) & 0xFF, line_number & 0xFF, 4 + len(body)))
        out += body
    out += b"\x0d\xff"
    return bytes(out)


class TestLineFraming:
    def test_empty_program(self):
        assert detokenise(b"\x0d\xff") == ""

    def test_single_line(self):
        # 10<space>PRINT  ->  body is space + PRINT token.
        assert detokenise(_program((10, b"\x20\xf1"))) == "10 PRINT\n"

    def test_multiple_lines_in_order(self):
        program = _program((10, b"\x20\xf1"), (20, b"\x20\xe0"))
        assert detokenise(program) == "10 PRINT\n20 END\n"

    def test_line_number_is_big_endian_in_header(self):
        # Line 258 = 0x0102.
        assert detokenise(_program((258, b"\x20\xe0"))).startswith("258 END")


class TestBodyExpansion:
    def test_keyword_token_expands(self):
        assert detokenise(_program((10, b"\xf1"))) == "10PRINT\n"

    def test_line_number_reference_decodes(self):
        # 10 GOTO 100 : space, GOTO(&E5), space, &8D + encode(100).
        body = b"\x20\xe5\x20\x8d\x44\x64\x40"
        assert detokenise(_program((10, body))) == "10 GOTO 100\n"

    def test_assignment_form_pseudo_variable(self):
        # &D0 is the assignment form of PAGE.
        assert detokenise(_program((10, b"\x20\xd0\x3d\x30"))) == "10 PAGE=0\n"

    def test_bytes_in_a_string_are_literal_not_tokens(self):
        # &C8 is the LOAD token, but inside quotes it must stay a raw char.
        body = b"\x20\xf1\x20\x22\xc8\x22"  # space PRINT space "<C8>"
        result = detokenise(_program((10, body)))
        assert result == "10 PRINT " + '"' + chr(0xC8) + '"' + "\n"
        assert "LOAD" not in result

    def test_escaped_quote_pair_round_of_toggles(self):
        # "a""b" is the BASIC source for the string  a"b .
        body = b"\x22\x61\x22\x22\x62\x22"
        assert detokenise(_program((10, body))) == '10"a""b"\n'


class TestMalformed:
    def test_missing_line_marker_reports_offset_and_byte(self):
        with pytest.raises(MissingLineMarkerError) as excinfo:
            detokenise(b"\x99\x00\x0a\x05\xf1\x0d\xff")
        assert excinfo.value.offset == 0
        assert excinfo.value.found == 0x99
        assert "&99" in str(excinfo.value)

    def test_truncated_line_reference_reports_absolute_offset(self):
        # &8D with only two payload bytes before the line ends. The &8D
        # sits at offset 4 (after the 0D 00 0A 05 header).
        with pytest.raises(TruncatedProgramError) as excinfo:
            detokenise(_program((10, b"\x8d\x44\x64")))
        assert excinfo.value.offset == 4
        assert "&8D" in str(excinfo.value)

    def test_impossible_length_byte(self):
        # length = 1 is below the 4-byte header minimum.
        with pytest.raises(InvalidLineLengthError) as excinfo:
            detokenise(b"\x0d\x00\x0a\x01\x0d\xff")
        assert excinfo.value.length == 1

    def test_errors_are_detokenise_errors(self):
        with pytest.raises(DetokeniseError):
            detokenise(b"\x99")

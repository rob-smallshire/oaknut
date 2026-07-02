"""Tests for the structural tokenised-BBC-BASIC detector.

The detector walks the &0D-framed line structure the same way the ROM's
``LIST`` does, but is *tolerant*: unlike :func:`scan_program`, which
raises on malformed input, :func:`detect` classifies any blob — clean
program, program-plus-data, truncated fragment, or arbitrary garbage —
into a :class:`Verdict` with evidence, and never raises.
"""

import pytest
from oaknut.basic import Detection, Verdict, detect, tokenise


def _program(*lines: tuple[int, bytes]) -> bytes:
    """Frame (line_number, body) pairs into a tokenised program."""
    out = bytearray()
    for line_number, body in lines:
        out += bytes((0x0D, (line_number >> 8) & 0xFF, line_number & 0xFF, 4 + len(body)))
        out += body
    out += b"\x0d\xff"
    return bytes(out)


class TestClean:
    def test_tokenised_program_is_basic(self):
        program = tokenise("10 PRINT \"HELLO\"\n20 GOTO 10")
        result = detect(program)
        assert result.verdict is Verdict.BASIC
        assert result.is_basic
        assert result.line_count == 2
        assert result.first_line == 10
        assert result.last_line == 20
        assert result.trailing_length == 0
        assert result.program_length == len(program)
        assert result.ascending

    def test_reason_reports_the_line_count(self):
        result = detect(tokenise("10 END"))
        assert "1 line" in result.reason

    def test_single_bodyless_line_is_basic(self):
        # A line with only its 4-byte header (no body) is well-formed.
        result = detect(_program((10, b"")))
        assert result.verdict is Verdict.BASIC
        assert result.line_count == 1


class TestTrailing:
    def test_program_with_appended_data_is_basic_trailing(self):
        program = tokenise("10 PRINT")
        blob = program + b"junk appended after the terminator"
        result = detect(blob)
        assert result.verdict is Verdict.BASIC_TRAILING
        assert result.is_basic
        assert result.trailing_length == len(b"junk appended after the terminator")
        assert result.program_length == len(program)
        assert "trailing" in result.reason


class TestMaybe:
    def test_truncated_mid_line_is_maybe(self):
        # One clean line, then a second line header whose length runs off
        # the end: it begins as BASIC but the structure breaks.
        blob = _program((10, b"PRINT"))[:-2]  # drop the terminator
        blob = blob + b"\x0d\x00\x14\x40"  # a line claiming 0x40 body bytes
        result = detect(blob)
        assert result.verdict is Verdict.MAYBE
        assert not result.is_basic
        assert result.line_count == 1

    def test_first_line_length_too_small_after_one_good_line(self):
        good = _program((10, b"AB"))[:-2]  # first line, no terminator
        blob = good + b"\x0d\x00\x14\x03"  # second line header, length 3 (< 4)
        result = detect(blob)
        assert result.verdict is Verdict.MAYBE
        assert "length 3" in result.reason


class TestNotBasic:
    def test_not_cr_led_is_not_basic(self):
        result = detect(b"This is just some text.")
        assert result.verdict is Verdict.NOT_BASIC
        assert not result.is_basic
        assert "not a &0D line marker" in result.reason

    def test_leading_cr_terminator_with_no_lines_is_not_basic(self):
        # A View document opening 0x0D 0x80: a terminator before any line.
        result = detect(b"\x0d\x80the rest of a view document")
        assert result.verdict is Verdict.NOT_BASIC
        assert result.line_count == 0

    def test_too_short_is_not_basic(self):
        assert detect(b"").verdict is Verdict.NOT_BASIC
        assert detect(b"\x0d").verdict is Verdict.NOT_BASIC

    def test_first_header_malformed_is_not_basic(self):
        # 0x0D, a line-number high byte, then it runs out: zero clean lines.
        result = detect(b"\x0d\x00\x0a")  # truncated first header
        assert result.verdict is Verdict.NOT_BASIC


class TestTerminatorTolerance:
    def test_non_ff_top_bit_terminator_is_basic_with_note(self):
        program = bytearray(tokenise("10 PRINT"))
        # Tamper with the terminator's second byte: top bit still set.
        assert program[-1] == 0xFF
        program[-1] = 0x80
        result = detect(bytes(program))
        assert result.verdict is Verdict.BASIC
        assert result.is_basic
        assert any("not &FF" in note for note in result.notes)

    def test_ff_terminator_has_no_note(self):
        assert detect(tokenise("10 PRINT")).notes == ()


class TestEvidence:
    def test_descending_line_numbers_flagged_not_ascending(self):
        # Structurally valid, but line numbers go down: still BASIC.
        blob = _program((20, b"A"), (10, b"B"))
        result = detect(blob)
        assert result.verdict is Verdict.BASIC
        assert result.ascending is False
        assert result.first_line == 20
        assert result.last_line == 10

    def test_notes_is_immutable_sequence(self):
        # Evidence is a frozen result; notes must not be a mutable list a
        # caller could accidentally extend.
        result = detect(tokenise("10 END"))
        assert isinstance(result, Detection)
        with pytest.raises((AttributeError, TypeError)):
            result.verdict = Verdict.NOT_BASIC  # frozen dataclass


class TestNeverRaises:
    @pytest.mark.parametrize(
        "blob",
        [
            b"",
            b"\x0d",
            b"\x0d\x0d\x0d\x0d",
            b"\x0d\x00\x0a\xff",  # header length byte 0xFF
            b"\x0d\x00\x0a\x04",  # bodyless-length line then nothing
            bytes(range(256)),
            b"\x0d" + bytes(range(256)),
        ],
    )
    def test_detect_is_total(self, blob: bytes):
        # Must classify, never throw, whatever the input.
        result = detect(blob)
        assert isinstance(result.verdict, Verdict)

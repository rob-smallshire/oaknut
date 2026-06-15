"""Tests for the &8D line-number reference codec.

The worked examples come straight from the disassembly notes; the
round-trip and no-&0D properties were stated as verified-by-simulation
there and are re-checked here across the whole valid range.
"""

from oaknut.basic.linenumber import (
    MAX_LINE_NUMBER,
    decode_line_number,
    encode_line_number,
)


class TestWorkedExamples:
    # (line number, the three payload bytes after &8D)
    EXAMPLES = [
        (1, b"\x54\x41\x40"),
        (10, b"\x54\x4a\x40"),
        (100, b"\x44\x64\x40"),
        (1000, b"\x64\x68\x43"),
        (32767, b"\x60\x7f\x7f"),
    ]

    def test_encode_matches_disassembly(self):
        for line_number, expected in self.EXAMPLES:
            assert encode_line_number(line_number) == expected

    def test_decode_matches_disassembly(self):
        for line_number, payload in self.EXAMPLES:
            assert decode_line_number(payload) == line_number


class TestRoundTrip:
    def test_round_trips_whole_valid_range(self):
        for line_number in range(0, MAX_LINE_NUMBER + 1):
            assert decode_line_number(encode_line_number(line_number)) == line_number

    def test_no_encoded_byte_is_ever_cr(self):
        # The whole point of the scramble: never embed &0D (the line
        # terminator) in a reference.
        for line_number in range(0, MAX_LINE_NUMBER + 1):
            assert 0x0D not in encode_line_number(line_number)


class TestValidation:
    def test_encode_rejects_out_of_range(self):
        for bad in (-1, 0x10000):
            try:
                encode_line_number(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"expected ValueError for {bad}")

    def test_decode_rejects_wrong_length(self):
        for bad in (b"", b"\x40", b"\x40\x40", b"\x40\x40\x40\x40"):
            try:
                decode_line_number(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"expected ValueError for {bad!r}")

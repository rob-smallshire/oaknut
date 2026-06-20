"""Tests for the BBC BASIC II token-stream scanner.

The scanner is the faithful primitive: where the de-tokeniser flattens a
body to text (lossy for keyword adjacency), :func:`scan` yields a token
per keyword, literal run, string, and line-number reference, each with
its byte offset. The headline case is ``?Q <PLOT> ?Q``, whose text
``?QPLOT?Q`` re-lexes as the variable ``QPLOT`` — only the stream keeps
``PLOT`` as a distinct token.
"""

import pytest
from oaknut.basic import (
    LineRecord,
    Token,
    TokenKind,
    detokenise_body,
    scan,
    scan_program,
)
from oaknut.basic.exceptions import (
    MissingLineMarkerError,
    TruncatedProgramError,
)
from oaknut.basic.linenumber import encode_line_number
from oaknut.basic.tokens import LINE_NUMBER_TOKEN


def _kinds(tokens):
    return [token.kind for token in tokens]


def _values(tokens):
    return [token.value for token in tokens]


class TestBodyScan:
    def test_empty_body_yields_no_tokens(self):
        assert list(scan(b"")) == []

    def test_plain_text_is_one_run(self):
        tokens = list(scan(b"A=1"))
        assert tokens == [Token(TokenKind.TEXT, "A=1", 0)]

    def test_keyword_resolves_to_spelling(self):
        # &F1 is PRINT.
        tokens = list(scan(b"\xf1"))
        assert tokens == [Token(TokenKind.KEYWORD, "PRINT", 0, 0xF1)]

    def test_keyword_splits_surrounding_text(self):
        # The rheolism case: ?Q <PLOT=&F0> ?Q must keep PLOT distinct.
        tokens = list(scan(b"?Q\xf0?Q"))
        assert _kinds(tokens) == [TokenKind.TEXT, TokenKind.KEYWORD, TokenKind.TEXT]
        assert _values(tokens) == ["?Q", "PLOT", "?Q"]
        assert tokens[1].token == 0xF0
        assert [token.start for token in tokens] == [0, 2, 3]

    def test_string_is_copied_verbatim_through_the_quotes(self):
        # Token-valued bytes inside a string must not expand.
        tokens = list(scan(b'"\xf0"'))
        assert tokens == [Token(TokenKind.STRING, '"\xf0"', 0)]

    def test_unterminated_string_runs_to_end(self):
        tokens = list(scan(b'X"ab'))
        assert _kinds(tokens) == [TokenKind.TEXT, TokenKind.STRING]
        assert _values(tokens) == ["X", '"ab']

    def test_line_number_reference_is_decoded(self):
        body = b"\xe5" + bytes((LINE_NUMBER_TOKEN,)) + encode_line_number(100)
        tokens = list(scan(body))
        assert _kinds(tokens) == [TokenKind.KEYWORD, TokenKind.LINENUM]
        assert tokens[0].value == "GOTO"
        assert tokens[1] == Token(TokenKind.LINENUM, "100", 1)

    def test_unknown_high_byte_folds_into_text(self):
        # &CE is the unused gap: no keyword, but must survive as a byte.
        tokens = list(scan(b"A\xceB"))
        assert tokens == [Token(TokenKind.TEXT, "A\xceB", 0)]

    def test_base_offset_shifts_reported_positions(self):
        tokens = list(scan(b"\xf0", base_offset=10))
        assert tokens[0].start == 10

    def test_truncated_line_number_reference_raises(self):
        with pytest.raises(TruncatedProgramError):
            list(scan(bytes((LINE_NUMBER_TOKEN, 0x40, 0x40))))


class TestDetokeniseBodyProjection:
    """detokenise_body is exactly the text join of the token stream."""

    @pytest.mark.parametrize(
        "body",
        [
            b"",
            b"A=1",
            b"?Q\xf0?Q",
            b'PRINT"\xf0\xf1"',
            b"\xe5" + bytes((LINE_NUMBER_TOKEN,)) + encode_line_number(2000),
            b"A\xceB",
            b'X"ab',
        ],
    )
    def test_body_text_is_the_joined_values(self, body):
        assert detokenise_body(body) == "".join(token.value for token in scan(body))

    def test_inline_token_body_detokenises_without_framing(self):
        # The #39 case: a headerless inline-token body the framed
        # detokenise() would reject at offset 0.
        assert detokenise_body(b"\xeb\x37") == "MODE7"


class TestProgramScan:
    def _program(self, *lines):
        out = bytearray()
        for line_number, body in lines:
            out += bytes((0x0D, (line_number >> 8) & 0xFF, line_number & 0xFF, 4 + len(body)))
            out += body
        out += b"\x0d\xff"
        return bytes(out)

    def test_walks_records_and_yields_line_numbers(self):
        program = self._program((10, b"\xeb\x37"), (20, b"?Q\xf0?Q"))
        records = list(scan_program(program))
        assert [record.line_number for record in records] == [10, 20]
        assert all(isinstance(record, LineRecord) for record in records)
        assert _values(records[1].tokens) == ["?Q", "PLOT", "?Q"]

    def test_record_start_points_at_the_cr_marker(self):
        program = self._program((10, b"X"), (20, b"Y"))
        records = list(scan_program(program))
        assert records[0].start == 0
        assert records[1].start == 5

    def test_empty_program_yields_no_records(self):
        assert list(scan_program(b"\x0d\xff")) == []

    def test_missing_line_marker_raises(self):
        with pytest.raises(MissingLineMarkerError):
            list(scan_program(b"\xeb"))


class TestPublicTokenTable:
    """The byte-level surface a faithful front end consumes (#41)."""

    def test_table_symbols_are_exported_from_the_package(self):
        import oaknut.basic as basic

        for name in (
            "TOKEN_TO_KEYWORD",
            "KEYWORDS",
            "LINE_NUMBER_TOKEN",
            "decode_line_number",
            "FLAG_CONDITIONAL",
            "FLAG_MIDDLE",
            "FLAG_START",
            "FLAG_FN_PROC",
            "FLAG_LINE_NUMBER",
            "FLAG_STOP_LINE",
            "FLAG_PSEUDO_VAR",
        ):
            assert name in basic.__all__
            assert hasattr(basic, name)

    def test_token_to_keyword_resolves_a_keyword(self):
        from oaknut.basic import TOKEN_TO_KEYWORD

        assert TOKEN_TO_KEYWORD[0xF1] == "PRINT"

    def test_token_to_keyword_is_read_only(self):
        from oaknut.basic import TOKEN_TO_KEYWORD

        with pytest.raises(TypeError):
            TOKEN_TO_KEYWORD[0x00] = "OOPS"

    def test_line_number_helpers_round_trip(self):
        from oaknut.basic import LINE_NUMBER_TOKEN, decode_line_number

        assert LINE_NUMBER_TOKEN == 0x8D
        assert decode_line_number(encode_line_number(1234)) == 1234

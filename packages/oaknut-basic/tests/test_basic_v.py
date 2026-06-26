"""Tests for the BBC BASIC V (Archimedes/RISC OS) detokenising dialect.

BASIC V re-uses three BASIC II command tokens — ``&C6``/``&C7``/``&C8`` —
as two-byte *escape prefixes*: the following byte selects an extended
keyword (``SUM``, ``RENUMBER``, ``CASE``/``SYS``/``ORIGIN`` ...). It also
re-purposes several single-byte slots: ``&7F`` becomes ``OTHERWISE`` and
``&C9``-``&CE`` — ``LIST``/``NEW``/``OLD``/``RENUMBER``/``SAVE`` in
BASIC II — become the block keywords ``WHEN``/``OF``/``ENDCASE``/
``ELSE``/``ENDIF``/``ENDWHILE``. The default dialect stays BASIC II, so
the escape bytes still decode to ``AUTO``/``DELETE``/``LOAD`` unless the
caller opts into :data:`BASIC_V`.
"""

import pytest
from oaknut.basic import (
    BASIC_II,
    BASIC_V,
    Dialect,
    TokenKind,
    detokenise,
    detokenise_body,
    scan,
)


def _program(*lines: tuple[int, bytes]) -> bytes:
    """Frame (line_number, body) pairs into a tokenised program."""
    out = bytearray()
    for line_number, body in lines:
        out += bytes((0x0D, (line_number >> 8) & 0xFF, line_number & 0xFF, 4 + len(body)))
        out += body
    out += b"\x0d\xff"
    return bytes(out)


class TestEscapeStatements:
    """``&C8`` <byte> — extended statement tokens, second byte from &8E."""

    @pytest.mark.parametrize(
        ("second", "keyword"),
        [
            (0x8E, "CASE"),
            (0x8F, "CIRCLE"),
            (0x90, "FILL"),
            (0x91, "ORIGIN"),
            (0x92, "POINT"),
            (0x93, "RECTANGLE"),
            (0x94, "SWAP"),
            (0x95, "WHILE"),
            (0x96, "WAIT"),
            (0x97, "MOUSE"),
            (0x98, "QUIT"),
            (0x99, "SYS"),
            (0x9A, "INSTALL"),
            (0x9B, "LIBRARY"),
            (0x9C, "TINT"),
            (0x9D, "ELLIPSE"),
            (0x9E, "BEATS"),
            (0x9F, "TEMPO"),
            (0xA0, "VOICES"),
            (0xA1, "VOICE"),
            (0xA2, "STEREO"),
            (0xA3, "OVERLAY"),
        ],
    )
    def test_c8_escape_decodes_to_statement(self, second: int, keyword: str):
        assert detokenise_body(bytes((0xC8, second)), dialect=BASIC_V) == keyword


class TestEscapeCommands:
    """``&C7`` <byte> — extended command tokens, second byte from &8E."""

    @pytest.mark.parametrize(
        ("second", "keyword"),
        [
            (0x8E, "APPEND"),
            (0x8F, "AUTO"),
            (0x90, "CRUNCH"),
            (0x91, "DELETE"),
            (0x92, "EDIT"),
            (0x93, "HELP"),
            (0x94, "LIST"),
            (0x95, "LOAD"),
            (0x96, "LVAR"),
            (0x97, "NEW"),
            (0x98, "OLD"),
            (0x99, "RENUMBER"),
            (0x9A, "SAVE"),
            (0x9B, "TEXTLOAD"),
            (0x9C, "TEXTSAVE"),
            (0x9D, "TWIN"),
            (0x9E, "TWINO"),
            (0x9F, "INSTALL"),
        ],
    )
    def test_c7_escape_decodes_to_command(self, second: int, keyword: str):
        assert detokenise_body(bytes((0xC7, second)), dialect=BASIC_V) == keyword


class TestEscapeFunctions:
    """``&C6`` <byte> — the two extended function tokens."""

    @pytest.mark.parametrize(("second", "keyword"), [(0x8E, "SUM"), (0x8F, "BEAT")])
    def test_c6_escape_decodes_to_function(self, second: int, keyword: str):
        assert detokenise_body(bytes((0xC6, second)), dialect=BASIC_V) == keyword


class TestSingleByteDifferences:
    """Single-byte tokens BASIC V re-purposes from BASIC II."""

    @pytest.mark.parametrize(
        ("token", "keyword"),
        [
            (0x7F, "OTHERWISE"),
            (0xC9, "WHEN"),
            (0xCA, "OF"),
            (0xCB, "ENDCASE"),
            (0xCC, "ELSE"),
            (0xCD, "ENDIF"),
            (0xCE, "ENDWHILE"),
        ],
    )
    def test_single_byte_token_decodes_to_basic_v_keyword(self, token: int, keyword: str):
        assert detokenise_body(bytes((token,)), dialect=BASIC_V) == keyword

    def test_shared_single_byte_tokens_are_unchanged(self):
        # Tokens common to both dialects still decode the same way.
        assert detokenise_body(b"\xf1", dialect=BASIC_V) == "PRINT"
        assert detokenise_body(b"\x8f", dialect=BASIC_V) == "PTR"


class TestIssue44Reproduction:
    def test_origin_statement_is_not_loadtime(self):
        # Line 140 of "Herding (RR1)", Acorn User June 1991:
        #   C8 91 " 640,512"  ->  ORIGIN 640,512   (was: LOADTIME 640,512)
        body = bytes((0xC8, 0x91)) + b" 640,512"
        assert detokenise_body(body, dialect=BASIC_V) == "ORIGIN 640,512"

    def test_program_round_through_detokenise(self):
        program = _program((140, bytes((0xC8, 0x91)) + b" 640,512"))
        assert detokenise(program, dialect=BASIC_V) == "140ORIGIN 640,512\n"


class TestDefaultDialectUnchanged:
    """Without opting in, the escape bytes keep their BASIC II meaning."""

    def test_c8_defaults_to_load_plus_token(self):
        body = bytes((0xC8, 0x91)) + b" 640,512"
        assert detokenise_body(body) == "LOADTIME 640,512"

    def test_default_dialect_is_basic_ii(self):
        body = bytes((0xC8, 0x91))
        assert detokenise_body(body, dialect=BASIC_II) == detokenise_body(body)

    def test_basic_v_c9_is_list_under_basic_ii(self):
        assert detokenise_body(b"\xc9") == "LIST"


class TestScanStream:
    def test_escape_token_is_one_keyword_advancing_two_bytes(self):
        body = bytes((0xC8, 0x99)) + b"X"  # SYS then a literal X
        tokens = list(scan(body, dialect=BASIC_V))
        assert tokens[0].kind is TokenKind.KEYWORD
        assert tokens[0].value == "SYS"
        assert tokens[0].start == 0
        assert tokens[1].kind is TokenKind.TEXT
        assert tokens[1].value == "X"
        assert tokens[1].start == 2

    def test_escape_byte_inside_string_stays_literal(self):
        body = b'"' + bytes((0xC8, 0x91)) + b'"'
        tokens = list(scan(body, dialect=BASIC_V))
        assert len(tokens) == 1
        assert tokens[0].kind is TokenKind.STRING
        assert tokens[0].value == '"\xc8\x91"'

    def test_unterminated_escape_prefix_stays_literal(self):
        # A trailing &C8 with no following byte must not over-read.
        tokens = list(scan(b"\xc8", dialect=BASIC_V))
        assert tokens[0].kind is TokenKind.TEXT
        assert tokens[0].value == "\xc8"


class TestDialectObject:
    def test_basic_v_has_a_name(self):
        assert isinstance(BASIC_V, Dialect)
        assert "V" in BASIC_V.name

    def test_unknown_escape_second_byte_is_left_literal(self):
        # &C8 followed by a byte with no extended-token meaning: emit the
        # prefix as a literal rather than inventing a keyword or over-reading.
        body = bytes((0xC8, 0x41))  # &41 = 'A', not an extended statement
        tokens = list(scan(body, dialect=BASIC_V))
        assert tokens[0].kind is TokenKind.TEXT
        assert tokens[0].value.startswith("\xc8")

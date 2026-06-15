"""Tests for the BBC BASIC II tokeniser.

Unit tests assert exact body bytes for each crunch rule (keywords,
abbreviations, conditional suppression, pseudo-variables, line-number
arming, the REM/DATA/string/star suppression contexts). Round-trip tests
then pin the whole thing against the de-tokeniser, including the real
``ragged.bas`` program.
"""

from pathlib import Path

import oaknut.basic as basic
import pytest
from oaknut.basic import detokenise, tokenise
from oaknut.basic.exceptions import (
    AlreadyNumberedError,
    LineNumberOrderError,
    LineNumberRangeError,
    LineTooLongError,
    UnnumberedLineError,
)

_DATA_DIRPATH = Path(__file__).parent / "data"


def _body(statement: str) -> bytes:
    """Tokenise a single body (no leading space) and return its bytes."""
    program = tokenise("10" + statement)
    length = program[3]
    return program[4:length]


class TestFraming:
    def test_empty_program_is_just_the_end_marker(self):
        assert tokenise("") == b"\x0d\xff"

    def test_blank_lines_are_skipped(self):
        assert tokenise("\n   \n") == b"\x0d\xff"

    def test_single_line_layout(self):
        # 10<space>END : header 0D 00 0A 06, body 20 E0, then 0D FF.
        assert tokenise("10 END") == b"\x0d\x00\x0a\x06\x20\xe0\x0d\xff"

    def test_line_number_is_big_endian(self):
        program = tokenise("258 END")  # 258 = 0x0102
        assert program[1] == 0x01
        assert program[2] == 0x02


class TestKeywords:
    def test_simple_keyword(self):
        assert _body("PRINT") == b"\xf1"

    def test_keyword_then_operator(self):
        assert _body("PRINT;") == b"\xf1;"

    def test_spaces_are_preserved(self):
        assert _body("  PRINT") == b"  \xf1"

    def test_greedy_keyword_inside_a_name(self):
        # AND is not conditional, so ANDY tokenises AND then "Y".
        assert _body("ANDY") == b"\x80Y"


class TestAbbreviations:
    def test_single_letter_abbreviation(self):
        assert _body("P.") == b"\xf1"  # PRINT

    def test_longer_prefix_picks_later_entry(self):
        assert _body("PRO.") == b"\xf2"  # PROC
        assert _body("PR.") == b"\xf1"  # still PRINT


class TestConditional:
    def test_keyword_followed_by_name_char_stays_a_name(self):
        # END is conditional; ENDX is a variable, not END + X.
        assert _body("ENDX") == b"ENDX"

    def test_bare_keyword_still_tokenises(self):
        assert _body("END") == b"\xe0"

    def test_longer_keyword_wins_by_table_order(self):
        assert _body("ENDPROC") == b"\xe1"


class TestPseudoVariables:
    def test_assignment_form_at_statement_start(self):
        # PAGE at the start of a statement is the assignment token &D0.
        assert _body("PAGE=&2000")[0] == 0xD0

    def test_function_form_mid_statement(self):
        # PAGE read as a value is the function token &90.
        assert _body("X=PAGE") == b"X=\x90"


class TestLineNumberReferences:
    def test_goto_encodes_its_target(self):
        # space GOTO space &8D + encode(100)
        assert _body(" GOTO 100") == b"\x20\xe5\x20\x8d\x44\x64\x40"

    def test_comma_keeps_arming_for_on_goto_lists(self):
        body = _body("ON X GOTO 10,20")
        # Both list entries are encoded as line numbers.
        assert body.count(b"\x8d") == 2

    def test_variable_target_is_not_encoded(self):
        # GOTO of a variable leaves the name alone (no &8D).
        assert b"\x8d" not in _body(" GOTO X")


class TestSuppressionContexts:
    def test_rem_leaves_the_rest_literal(self):
        assert _body("REM PRINT") == b"\xf4 PRINT"

    def test_data_leaves_the_rest_literal_including_colons(self):
        assert _body("DATA 1:X") == b"\xdc 1:X"

    def test_tokens_inside_a_string_are_literal(self):
        assert _body('PRINT "GOTO"') == b'\xf1 "GOTO"'

    def test_statement_leading_star_is_literal(self):
        assert _body("*CAT") == b"*CAT"

    def test_mid_statement_star_is_multiply(self):
        assert _body("X=3*4") == b"X=3*4"


class TestErrors:
    def test_unnumbered_line(self):
        with pytest.raises(UnnumberedLineError) as excinfo:
            tokenise("PRINT")
        assert excinfo.value.line_index == 1

    def test_already_numbered_under_auto(self):
        with pytest.raises(AlreadyNumberedError) as excinfo:
            tokenise("10 PRINT", start=10)
        assert excinfo.value.line_number == 10

    def test_line_number_out_of_range(self):
        with pytest.raises(LineNumberRangeError):
            tokenise("70000 END")

    def test_referenced_line_number_out_of_range(self):
        with pytest.raises(LineNumberRangeError):
            tokenise("10 GOTO 70000")

    def test_line_numbers_must_ascend(self):
        with pytest.raises(LineNumberOrderError) as excinfo:
            tokenise("20 PRINT\n10 END")
        assert excinfo.value.previous_line_number == 20

    def test_line_too_long(self):
        with pytest.raises(LineTooLongError) as excinfo:
            tokenise("10 " + "A" * 300)
        assert excinfo.value.length > 251


class TestAutoNumbering:
    def test_auto_number_matches_manual_numbering(self):
        assert tokenise("PRINT\nEND", start=10, step=10) == tokenise("10 PRINT\n20 END")

    def test_step_defaults_when_only_start_given(self):
        assert tokenise("A\nB", start=100) == tokenise("100 A\n110 B")

    def test_start_defaults_when_only_step_given(self):
        assert tokenise("A\nB", step=5) == tokenise("10 A\n15 B")


class TestRoundTrip:
    def test_bytes_round_trip(self):
        program = tokenise("10 PRINT\n20 GOTO 10")
        assert tokenise(detokenise(program)) == program

    def test_text_round_trip(self):
        source = "10 PRINT\n20 GOTO 10"
        assert detokenise(tokenise(source)).rstrip("\n") == source

    def test_ragged_program_round_trips(self):
        numbered = basic.number_lines((_DATA_DIRPATH / "ragged.bas").read_text())
        program = tokenise(numbered)
        # Byte-exact: re-tokenising the de-tokenised program reproduces it.
        assert tokenise(detokenise(program)) == program
        # And the de-tokenised text matches the numbered source.
        assert detokenise(program).rstrip("\n") == numbered.rstrip("\n")

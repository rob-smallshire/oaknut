"""Tests for the line-numbering facade.

The :func:`oaknut.basic.number_lines` facade is the programmatic entry
point behind the ``oaknut-basic number`` CLI command; it works purely on
Python strings so it can be exercised without any disc image or stream
plumbing.
"""

from pathlib import Path

import oaknut.basic as basic
import pytest

_DATA_DIRPATH = Path(__file__).parent / "data"


class TestNumberLines:
    def test_numbers_each_line_from_ten_in_tens(self):
        source = "PRINT \"Hello\"\nEND"
        assert basic.number_lines(source) == "10 PRINT \"Hello\"\n20 END"

    def test_custom_step(self):
        source = "A\nB\nC"
        assert basic.number_lines(source, step=5) == "10 A\n15 B\n20 C"

    def test_custom_start(self):
        source = "A\nB"
        assert basic.number_lines(source, start=100) == "100 A\n110 B"

    def test_custom_start_and_step(self):
        source = "A\nB\nC"
        assert basic.number_lines(source, start=1, step=1) == "1 A\n2 B\n3 C"

    def test_single_line_without_trailing_newline(self):
        assert basic.number_lines("PRINT") == "10 PRINT"

    def test_trailing_newline_is_preserved(self):
        assert basic.number_lines("PRINT\nEND\n") == "10 PRINT\n20 END\n"

    def test_carriage_return_line_endings_are_accepted(self):
        # Acorn-native text uses a bare CR terminator.
        assert basic.number_lines("PRINT\rEND") == "10 PRINT\n20 END"

    def test_empty_source_yields_empty_string(self):
        assert basic.number_lines("") == ""

    def test_blank_lines_are_numbered_too(self):
        assert basic.number_lines("A\n\nB") == "10 A\n20 \n30 B"

    def test_control_codes_in_string_literal_do_not_split_the_line(self):
        # VDU / mode-7 control codes (here &0C, &1C) appear legitimately
        # inside string literals; str.splitlines() would break on them,
        # corrupting a single program line into several numbered lines.
        source = 'PRINT "' + chr(0x0C) + chr(0x1C) + 'banner"'
        assert basic.number_lines(source) == '10 PRINT "\x0c\x1cbanner"'

    def test_internal_references_are_left_untouched(self):
        # The facade only prepends numbers; it does not rewrite GOTO etc.
        source = "GOTO 20\nEND"
        assert basic.number_lines(source) == "10 GOTO 20\n20 END"


class TestRealProgram:
    """Number a real, hand-written BBC BASIC program.

    ``ragged.bas`` is a complete dynamic-programming line-breaker with
    no leading line numbers, but its ``GOTO`` targets are absolute
    numbers written for the BBC's default ``AUTO 10,10``. Numbering at
    the default 10/step-10 must therefore reproduce those exact targets,
    or the reconstructed program would no longer run — the strongest
    end-to-end check that numbering preserves a program's structure.
    """

    @pytest.fixture
    def source(self) -> str:
        return (_DATA_DIRPATH / "ragged.bas").read_text()

    def test_first_line_is_numbered_ten(self, source: str):
        numbered = basic.number_lines(source)
        assert numbered.splitlines()[0] == "10 REM ==============================="

    def test_every_line_is_numbered_in_tens(self, source: str):
        for index, line in enumerate(basic.number_lines(source).splitlines()):
            assert line.startswith(f"{(index + 1) * 10} ")

    def test_absolute_goto_targets_land_on_the_right_lines(self, source: str):
        numbered = basic.number_lines(source)
        by_number = {int(line.split(" ", 1)[0]): line for line in numbered.splitlines()}
        # Each jump in the source assumes these post-numbering targets.
        assert by_number[740] == "740 REM space between lines"
        assert by_number[1030] == "1030 IF text%?p% = 13 THEN done%=TRUE: GOTO 1180"
        assert by_number[1130] == "1130 wordlen%(words_count%) = l%"
        assert by_number[1180] == "1180 UNTIL done%"
        assert by_number[1550] == "1550 cost%(i%) = best%"


class TestNumberLinesValidation:
    def test_step_below_one_is_rejected(self):
        with pytest.raises(ValueError):
            basic.number_lines("A\nB", step=0)

    def test_negative_start_is_rejected(self):
        with pytest.raises(ValueError):
            basic.number_lines("A\nB", start=-1)

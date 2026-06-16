"""Tests for the shared report-rendering cell helpers."""

from __future__ import annotations

from asyoulikeit import ByAudience
from oaknut.cli import control_pictures, text_cell


class TestControlPictures:
    def test_c0_controls_map_to_pictures_block(self):
        # Every C0 control (0x00–0x1F) maps to U+2400 + codepoint.
        for c in range(0x20):
            assert control_pictures(chr(c)) == chr(0x2400 + c)

    def test_del_maps_to_its_symbol(self):
        assert control_pictures("\x7f") == "␡"  # ␡

    def test_printable_text_unchanged(self):
        assert control_pictures("Pascal 1.2 (c)") == "Pascal 1.2 (c)"

    def test_mixed_title(self):
        # The Oxford Pascal disc title: form-feed, then "Pascal", LF, CR.
        assert control_pictures("\x0cPascal\n\r") == "␌Pascal␊␍"


class TestTextCell:
    def test_clean_text_is_plain_string(self):
        # No control characters → no need to wrap; output is identical to
        # passing the bare string, keeping the common case untouched.
        assert text_cell("HELLO") == "HELLO"
        assert not isinstance(text_cell("HELLO"), ByAudience)

    def test_control_text_is_audience_aware(self):
        cell = text_cell("\x0cPascal\n\r")
        assert isinstance(cell, ByAudience)
        # Machines keep the raw bytes; humans get control pictures.
        assert cell.machine == "\x0cPascal\n\r"
        assert cell.human == "␌Pascal␊␍"

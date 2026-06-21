"""Tests for the shared report-rendering cell helpers."""

from __future__ import annotations

from asyoulikeit import ByAudience
from oaknut.cli import address_cell, control_pictures, text_cell


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


class TestAddressCell:
    def test_machine_keeps_raw_int(self):
        cell = address_cell(0x1900)
        assert isinstance(cell, ByAudience)
        assert cell.machine == 0x1900

    def test_human_keeps_0x_prefix(self):
        assert address_cell(0x1900).human.startswith("0x")

    def test_human_trimmed_to_minimum_six_hexits(self):
        # Acorn MOS shows DFS addresses in six hex digits; leading zeros
        # beyond that serve no purpose, so the narrowest form is six.
        assert address_cell(0x1900).human == "0x001900"
        assert address_cell(0x838F).human == "0x00838F"
        assert address_cell(0x0).human == "0x000000"

    def test_human_grows_in_whole_bytes(self):
        # Above six hexits the width rounds up to an even number of hexits
        # (a whole number of bytes), never an odd count.
        assert address_cell(0xFFFFFF).human == "0xFFFFFF"
        assert address_cell(0x1FF0000).human == "0x01FF0000"
        assert address_cell(0xFFFF0E00).human == "0xFFFF0E00"

"""Tests for the RISC OS filetype name table and parser."""

from __future__ import annotations

import pytest
from oaknut.file.exceptions import InvalidFiletypeError
from oaknut.file.filetypes import filetype_name, parse_filetype


class TestFiletypeName:
    @pytest.mark.parametrize(
        "number,name",
        [
            (0xFFF, "Text"),
            (0xFFD, "Data"),
            (0xFFB, "BASIC"),
            (0xFEB, "Obey"),
            (0xFF9, "Sprite"),
        ],
    )
    def test_known(self, number, name):
        assert filetype_name(number) == name

    def test_unknown_falls_back_to_ampersand_hex(self):
        assert filetype_name(0x123) == "&123"

    def test_unknown_is_three_uppercase_hexits(self):
        assert filetype_name(0x00A) == "&00A"


class TestParseFiletype:
    @pytest.mark.parametrize("text", ["Text", "text", "TEXT"])
    def test_name_case_insensitive(self, text):
        assert parse_filetype(text) == 0xFFF

    @pytest.mark.parametrize(
        "text,value",
        [
            ("&fff", 0xFFF),
            ("&FFD", 0xFFD),
            ("0xFEB", 0xFEB),
            ("4095", 0xFFF),
            ("&00A", 0x00A),
        ],
    )
    def test_numeric_forms(self, text, value):
        assert parse_filetype(text) == value

    def test_round_trips_with_name(self):
        assert filetype_name(parse_filetype("Obey")) == "Obey"

    @pytest.mark.parametrize("text", ["", "Nonsense", "&1234", "0x1000", "-1"])
    def test_invalid_raises(self, text):
        with pytest.raises(InvalidFiletypeError):
            parse_filetype(text)

"""Tests for Access IntFlag enum and access formatting."""

import pytest

from oaknut_file.access import Access, format_access_hex, format_access_text


class TestAccessFlags:

    def test_owner_read_is_bit_0(self):
        assert Access.R == 0x01

    def test_owner_write_is_bit_1(self):
        assert Access.W == 0x02

    def test_execute_only_is_bit_2(self):
        assert Access.E == 0x04

    def test_locked_is_bit_3(self):
        assert Access.L == 0x08

    def test_public_read_is_bit_4(self):
        assert Access.PR == 0x10

    def test_public_write_is_bit_5(self):
        assert Access.PW == 0x20

    def test_combination(self):
        rw = Access.R | Access.W
        assert Access.R in rw
        assert Access.W in rw
        assert Access.L not in rw

    def test_integer_round_trip(self):
        flags = Access(0x0B)  # R | W | L
        assert Access.R in flags
        assert Access.W in flags
        assert Access.L in flags
        assert Access.E not in flags
        assert int(flags) == 0x0B

    def test_full_byte_round_trip(self):
        flags = Access(0x33)  # R | W | PR | PW
        assert Access.R in flags
        assert Access.W in flags
        assert Access.PR in flags
        assert Access.PW in flags
        assert int(flags) == 0x33

    def test_pieb_default_perm(self):
        """PiEconetBridge default perm 0x17 = PR | E | W | R."""
        flags = Access(0x17)
        assert Access.R in flags
        assert Access.W in flags
        assert Access.E in flags
        assert Access.PR in flags
        assert Access.L not in flags

    def test_empty(self):
        empty = Access(0)
        assert Access.R not in empty
        assert Access.W not in empty
        assert Access.L not in empty


class TestFormatAccessHex:

    def test_format_wr(self):
        assert format_access_hex(0x03) == "03"

    def test_format_locked(self):
        assert format_access_hex(0x0B) == "0B"

    def test_format_none(self):
        assert format_access_hex(None) == ""

    def test_format_zero(self):
        assert format_access_hex(0) == "00"

    def test_format_full(self):
        assert format_access_hex(0x33) == "33"


class TestFormatAccessText:

    def test_wr(self):
        result = format_access_text(0x03)
        assert "W" in result
        assert "R" in result

    def test_locked_read_only(self):
        result = format_access_text(0x09)  # L | R
        assert "L" in result
        assert "R" in result
        assert "W" not in result.split("/")[0]  # W not in owner part

    def test_public_read(self):
        result = format_access_text(0x13)  # PR | W | R
        parts = result.split("/")
        assert len(parts) == 2
        assert "R" in parts[1]  # public part has R

    def test_none(self):
        result = format_access_text(None)
        assert result == "/"

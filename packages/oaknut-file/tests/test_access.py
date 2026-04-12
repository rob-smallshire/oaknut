"""Tests for Access IntFlag enum and access formatting/parsing."""

import pytest
from oaknut.file.access import (
    Access,
    format_access_hex,
    format_access_text,
    parse_access,
)


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


class TestParseAccess:
    """Test parse_access() — the reverse of format_access_text/hex."""

    # Symbolic form: "owner/public" where letters are L, W, R, E / W, R
    def test_wr_slash_r(self):
        assert parse_access("WR/R") == Access.W | Access.R | Access.PR

    def test_lwr_slash_r(self):
        assert parse_access("LWR/R") == Access.L | Access.W | Access.R | Access.PR

    def test_r_slash_empty(self):
        assert parse_access("R/") == Access.R

    def test_empty_slash_empty(self):
        assert parse_access("/") == Access(0)

    def test_wr_slash_wr(self):
        assert parse_access("WR/WR") == Access.W | Access.R | Access.PW | Access.PR

    def test_locked_only(self):
        assert parse_access("L/") == Access.L

    def test_case_insensitive(self):
        assert parse_access("lwr/r") == Access.L | Access.W | Access.R | Access.PR

    def test_e_flag(self):
        assert parse_access("ER/") == Access.E | Access.R

    # No slash — treat as owner-only
    def test_no_slash_wr(self):
        assert parse_access("WR") == Access.W | Access.R

    # Hex form: 0x prefix
    def test_hex_0x0b(self):
        assert parse_access("0x0B") == Access(0x0B)

    def test_hex_0x33(self):
        assert parse_access("0x33") == Access(0x33)

    def test_hex_0x00(self):
        assert parse_access("0x00") == Access(0)

    # Bare hex (no 0x prefix) — two hex digits
    def test_bare_hex_0b(self):
        assert parse_access("0B") == Access(0x0B)

    def test_bare_hex_33(self):
        assert parse_access("33") == Access(0x33)

    # Round-trip: format then parse
    def test_round_trip_lwr_r(self):
        original = Access.L | Access.W | Access.R | Access.PR
        text = format_access_text(int(original))
        assert parse_access(text) == original

    def test_round_trip_wr_wr(self):
        original = Access.W | Access.R | Access.PW | Access.PR
        text = format_access_text(int(original))
        assert parse_access(text) == original

    def test_round_trip_empty(self):
        text = format_access_text(0)
        assert parse_access(text) == Access(0)

    # Error cases
    def test_invalid_letter_raises(self):
        with pytest.raises(ValueError, match="nrecogni"):
            parse_access("XWR/R")

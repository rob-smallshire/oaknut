"""Tests for Access IntFlag enum and access formatting/parsing."""

import pytest
from oaknut.file.access import (
    Access,
    format_access_hex,
    format_access_text,
    parse_access,
    parse_access_spec,
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

    def test_run_only_shows_execute(self):
        # Run-only is owner E without R (BeebWiki, File access). E is shown
        # only when the owner has neither R nor W, as FNf_access does.
        from oaknut.file import Access, parse_access

        assert format_access_text(int(Access.E)) == "E/"
        assert format_access_text(int(Access.E | Access.L)) == "LE/"
        assert parse_access("E/") == Access.E

    def test_execute_alongside_read_is_not_shown(self):
        from oaknut.file import Access

        assert format_access_text(int(Access.E | Access.R | Access.W)) == "WR/"
        assert format_access_text(int(Access.E | Access.R)) == "R/"

    def test_bit_six_is_not_run_only(self):
        # 0x40 is public execute in the Acorn byte, not a run-only flag.
        assert format_access_text(0x40) == "/"


class TestRunOnly:
    def test_execute_without_read_is_run_only(self):
        from oaknut.file import Access

        assert Access.E.is_run_only
        assert (Access.E | Access.L).is_run_only
        assert (Access.E | Access.PR).is_run_only

    def test_anything_readable_is_not_run_only(self):
        from oaknut.file import Access

        assert not (Access.E | Access.R).is_run_only
        assert not Access.WR.is_run_only
        assert not Access(0).is_run_only
        assert not Access.L.is_run_only

    def test_x_is_retired(self):
        import pytest
        from oaknut.file import Access, parse_access
        from oaknut.file.exceptions import InvalidAccessError

        assert not hasattr(Access, "X")
        with pytest.raises(InvalidAccessError, match="E without R"):
            parse_access("X/")


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
            parse_access("QWR/R")

    def test_invalid_input_raises_a_domain_error_that_is_also_a_value_error(self):
        # InvalidAccessError is a DataError (so the CLI boundary renders it
        # without a traceback) and a ValueError (so historical
        # ``except ValueError`` handlers keep working).
        from oaknut.exception import DataError
        from oaknut.file.exceptions import InvalidAccessError

        for bad in ("QWR/R", "WR/Q", "+L", "not-access"):
            with pytest.raises(InvalidAccessError) as info:
                parse_access(bad)
            assert isinstance(info.value, DataError)
            assert isinstance(info.value, ValueError)


class TestParseAccessSpec:
    """parse_access_spec compiles an absolute or incremental spec to a transform."""

    def test_absolute_spec_replaces_ignoring_current(self):
        transform = parse_access_spec("LWR/R")
        expected = Access.L | Access.W | Access.R | Access.PR
        assert transform(Access(0)) == expected
        # Absolute replaces wholesale — a current public-write flag is dropped.
        assert transform(Access.PW) == expected

    def test_absolute_hex_spec(self):
        assert parse_access_spec("0x0B")(Access.PW) == Access(0x0B)

    def test_plus_adds_owner_flag(self):
        assert parse_access_spec("+L")(Access.R) == Access.R | Access.L

    def test_minus_removes_owner_flag(self):
        assert parse_access_spec("-W")(Access.W | Access.R) == Access.R

    def test_combined_clauses_apply_left_to_right(self):
        assert parse_access_spec("+L-W")(Access.W | Access.R) == Access.R | Access.L

    def test_public_flags_via_slash(self):
        assert parse_access_spec("+R/R")(Access(0)) == Access.R | Access.PR
        assert parse_access_spec("-/R")(Access.PR | Access.R) == Access.R
        assert parse_access_spec("+/W")(Access.R) == Access.R | Access.PW

    def test_incremental_is_case_insensitive(self):
        assert parse_access_spec("+l")(Access(0)) == Access.L

    def test_incremental_is_idempotent(self):
        assert parse_access_spec("+L")(Access.L) == Access.L
        assert parse_access_spec("-E")(Access.R) == Access.R

    def test_unknown_letter_raises_immediately(self):
        # Validated at compile time, before any file is touched.
        from oaknut.file.exceptions import InvalidAccessError

        with pytest.raises(InvalidAccessError):
            parse_access_spec("+Q")

    def test_empty_operation_raises(self):
        from oaknut.file.exceptions import InvalidAccessError

        with pytest.raises(InvalidAccessError):
            parse_access_spec("+")
        with pytest.raises(InvalidAccessError):
            parse_access_spec("+L-")

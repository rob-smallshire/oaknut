"""Tests for INF sidecar file parsing and formatting."""

import pytest
from oaknut.file.access import Access
from oaknut.file.inf import (
    format_pieb_inf_line,
    format_trad_inf_line,
    parse_inf_line,
    read_inf_file,
    write_inf_file,
)
from oaknut.file.meta import AcornMeta


class TestParseInfLineTraditional:
    def test_basic_line(self):
        source, meta = parse_inf_line("HELLO    00001900 00008023 00000100")
        assert source == "inf-trad"
        assert meta.load_address == 0x1900
        assert meta.exec_address == 0x8023

    def test_with_access(self):
        source, meta = parse_inf_line("HELLO    00001900 00008023 00000100 03")
        assert meta.access == 0x03

    def test_with_locked_letter(self):
        """Handle the 'L' marker used by some ADFS exporters."""
        source, meta = parse_inf_line("SECRET   00001900 00008023 00000100 L")
        # J.G. Harston, "Storing Acorn/BBC metadata on other systems": an
        # access field starting with "L" is converted to "19" for Locked.
        assert meta.access == 0x19

    def test_with_locked_word(self):
        """Handle the 'Locked' marker used by some DFS exporters."""
        source, meta = parse_inf_line("$.HELLO 00001900 00008023 00000100 Locked")
        assert meta.access == 0x19  # LR/R

    def test_with_symbolic_access_wr(self):
        # DFS-style symbolic access in the attribute field. The valid
        # load/exec must not be discarded because the attr is not hex.
        source, meta = parse_inf_line("HELLO    00000800 0000B82B 0000353C WR")
        assert source == "inf-trad"
        assert meta.load_address == 0x800
        assert meta.exec_address == 0xB82B
        assert meta.access == int(Access.WR)

    def test_with_symbolic_access_owner_public(self):
        source, meta = parse_inf_line("HELLO    00001900 00008023 00000100 LWR/R")
        assert meta.access == int(Access.L | Access.W | Access.R | Access.PR)

    def test_unparseable_access_keeps_addresses(self):
        # A garbage attribute must not throw away the load/exec — the
        # addresses are the payload; only the unparseable attr is dropped.
        source, meta = parse_inf_line("HELLO    00000800 0000B82B 0000353C ZZ")
        assert meta.load_address == 0x800
        assert meta.exec_address == 0xB82B
        assert meta.access is None

    def test_large_addresses(self):
        source, meta = parse_inf_line("FILE     FFFF0E10 FFFF0E10 00000200")
        assert meta.load_address == 0xFFFF0E10

    def test_carries_the_inf_filename(self):
        # The traditional INF's first field is the Acorn name; it must be
        # recoverable so an importer can prefer it over a lossy host filename.
        source, meta = parse_inf_line("test8/3    00000800 0000B82B 0000353C WR")
        assert meta.name == "test8/3"

    def test_pieb_has_no_name(self):
        source, meta = parse_inf_line("0 ffffdd00 ffffdd00 17")
        assert meta.name is None


class TestParseInfLinePiEconetBridge:
    def test_basic_pieb_line(self):
        source, meta = parse_inf_line("0 ffffdd00 ffffdd00 17")
        assert source == "inf-pieb"
        assert meta.load_address == 0xFFFFDD00
        # PiEB perm 0x17 is locked owner R/W with public R: LWR/R (#70).
        assert meta.access == 0x1B

    def test_pieb_with_owner(self):
        source, meta = parse_inf_line("5 1900 8023 03")
        assert meta.load_address == 0x1900
        assert meta.exec_address == 0x8023


class TestParseInfLineEdgeCases:
    def test_empty_line_returns_none(self):
        assert parse_inf_line("") is None

    def test_whitespace_returns_none(self):
        assert parse_inf_line("   ") is None

    def test_single_field_returns_none(self):
        assert parse_inf_line("HELLO") is None


class TestFormatTradInfLine:
    def test_basic(self):
        line = format_trad_inf_line("HELLO", 0x1900, 0x8023, 0x100)
        assert "00001900" in line
        assert "00008023" in line
        assert "00000100" in line
        assert line.startswith("HELLO")

    def test_with_access(self):
        line = format_trad_inf_line("HELLO", 0x1900, 0x8023, 0x100, attr=0x03)
        assert "03" in line

    def test_without_access(self):
        line = format_trad_inf_line("HELLO", 0x1900, 0x8023, 0x100)
        # Should not have trailing access field
        parts = line.split()
        assert len(parts) == 4


class TestFormatPiebInfLine:
    def test_basic(self):
        line = format_pieb_inf_line(0x1900, 0x8023)
        assert "1900" in line
        assert "8023" in line

    def test_with_owner(self):
        line = format_pieb_inf_line(0x1900, 0x8023, owner=5)
        assert line.startswith("5 ")

    def test_owner_formatted_as_hex(self):
        """Owner is formatted in lowercase hex, not decimal."""
        line = format_pieb_inf_line(0x1900, 0x8023, owner=42)
        assert line.startswith("2a ")  # 42 in hex


class TestInfRoundTrip:
    def test_trad_round_trip(self):
        line = format_trad_inf_line("HELLO", 0x1900, 0x8023, 0x100, attr=0x03)
        source, meta = parse_inf_line(line)
        assert meta.load_address == 0x1900
        assert meta.exec_address == 0x8023
        assert meta.access == 0x03


class TestReadWriteInfFile:
    def test_write_and_read(self, tmp_path):
        filepath = tmp_path / "test.inf"
        line = format_trad_inf_line("HELLO", 0x1900, 0x8023, 0x100, attr=0x03)
        write_inf_file(filepath, line)

        result = read_inf_file(filepath)
        assert result is not None
        source, meta = result
        assert meta.load_address == 0x1900

    def test_read_nonexistent_returns_none(self, tmp_path):
        result = read_inf_file(tmp_path / "missing.inf")
        assert result is None


class TestHarstonDefaults:
    """Defaults from J.G. Harston's INF specification (mdfs.net
    Docs/Comp/BBC/Filing/Metadata): a missing access field is &33, and an
    access field starting with "L" is &19."""

    @pytest.mark.parametrize(
        "line",
        ["$.F 00001900 00008023 00000100", "$.F 00001900 00008023"],
    )
    def test_missing_access_is_33(self, line):
        _source, meta = parse_inf_line(line)
        assert meta.access == 0x33

    @pytest.mark.parametrize("token", ["L", "Locked", "LOCKED", "LWR"])
    def test_a_token_starting_with_l_is_19(self, token):
        _source, meta = parse_inf_line(f"$.F 00001900 00008023 00000100 {token}")
        assert meta.access == 0x19

    def test_an_owner_public_string_still_parses_as_written(self):
        _source, meta = parse_inf_line("$.F 00001900 00008023 00000100 LWR/R")
        assert meta.access == 0x1B

    def test_hex_access_is_the_acorn_byte(self):
        _source, meta = parse_inf_line("$.F 00001900 00008023 00000100 33")
        assert meta.access == 0x33

    def test_the_basic_three_field_line_parses(self):
        # BeebWiki: the basic INF line is name, load, exec.
        source, meta = parse_inf_line("$.DCONV 1900 801F")
        assert source == "inf-trad"
        assert (meta.load_address, meta.exec_address) == (0x1900, 0x801F)
        assert meta.name == "$.DCONV"

    def test_a_missing_exec_address_is_the_load_address(self):
        # J.G. Harston: IF exec$="" : exec$=load$
        _source, meta = parse_inf_line("$.DATA 3000")
        assert (meta.load_address, meta.exec_address) == (0x3000, 0x3000)

    def test_a_name_alone_is_not_an_inf_line(self):
        assert parse_inf_line("$.ONLY") is None

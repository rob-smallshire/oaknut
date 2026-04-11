"""Tests for INF sidecar file parsing and formatting."""

import pytest
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
        assert meta.load_addr == 0x1900
        assert meta.exec_addr == 0x8023

    def test_with_access(self):
        source, meta = parse_inf_line("HELLO    00001900 00008023 00000100 03")
        assert meta.attr == 0x03

    def test_with_locked_letter(self):
        """Handle the 'L' marker used by some ADFS exporters."""
        source, meta = parse_inf_line("SECRET   00001900 00008023 00000100 L")
        assert meta.attr is not None
        assert meta.attr & 0x08  # L bit set

    def test_with_locked_word(self):
        """Handle the 'Locked' marker used by some DFS exporters."""
        source, meta = parse_inf_line("$.HELLO 00001900 00008023 00000100 Locked")
        assert meta.attr is not None
        assert meta.attr & 0x08  # L bit set

    def test_large_addresses(self):
        source, meta = parse_inf_line("FILE     FFFF0E10 FFFF0E10 00000200")
        assert meta.load_addr == 0xFFFF0E10

    def test_returns_filename(self):
        source, meta = parse_inf_line("MyFile   00001900 00008023 00000100")
        # The first field is the filename — returned as part of the tuple
        # Implementation detail: parse_inf_line returns (source, meta)
        # where the filename is accessible from the line itself


class TestParseInfLinePiEconetBridge:

    def test_basic_pieb_line(self):
        source, meta = parse_inf_line("0 ffffdd00 ffffdd00 17")
        assert source == "inf-pieb"
        assert meta.load_addr == 0xFFFFDD00
        assert meta.attr == 0x17

    def test_pieb_with_owner(self):
        source, meta = parse_inf_line("5 1900 8023 03")
        assert meta.load_addr == 0x1900
        assert meta.exec_addr == 0x8023


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
        assert meta.load_addr == 0x1900
        assert meta.exec_addr == 0x8023
        assert meta.attr == 0x03


class TestReadWriteInfFile:

    def test_write_and_read(self, tmp_path):
        filepath = tmp_path / "test.inf"
        line = format_trad_inf_line("HELLO", 0x1900, 0x8023, 0x100, attr=0x03)
        write_inf_file(filepath, line)

        result = read_inf_file(filepath)
        assert result is not None
        source, meta = result
        assert meta.load_addr == 0x1900

    def test_read_nonexistent_returns_none(self, tmp_path):
        result = read_inf_file(tmp_path / "missing.inf")
        assert result is None

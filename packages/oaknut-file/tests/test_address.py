"""Tests for parse_address — load/exec address literal parser."""

import pytest
from oaknut.file.address import parse_address
from oaknut.file.exceptions import InvalidAddressError


class TestValidLiterals:
    def test_hex_prefix(self):
        assert parse_address("0x1900") == 0x1900

    def test_hex_uppercase_prefix(self):
        assert parse_address("0X8023") == 0x8023

    def test_bare_number_is_decimal(self):
        # The whole point: no prefix means decimal, not hex.
        assert parse_address("1900") == 1900

    def test_octal_prefix(self):
        assert parse_address("0o14400") == 0o14400

    def test_binary_prefix(self):
        assert parse_address("0b101") == 0b101

    def test_zero(self):
        assert parse_address("0") == 0


class TestInvalidLiterals:
    def test_acorn_ampersand_hex_rejected(self):
        with pytest.raises(InvalidAddressError):
            parse_address("&1900")

    def test_non_numeric_rejected(self):
        with pytest.raises(InvalidAddressError):
            parse_address("notanumber")

    def test_empty_rejected(self):
        with pytest.raises(InvalidAddressError):
            parse_address("")

    def test_float_rejected(self):
        with pytest.raises(InvalidAddressError):
            parse_address("12.5")

    def test_message_names_the_offending_value(self):
        with pytest.raises(InvalidAddressError, match=r"&3000"):
            parse_address("&3000")


class TestExceptionCategory:
    def test_is_data_error(self):
        """InvalidAddressError must reach the CLI as a DataError so the
        boundary renders it without a traceback and exits EX_DATAERR."""
        from oaknut.exception import DataError

        assert issubclass(InvalidAddressError, DataError)

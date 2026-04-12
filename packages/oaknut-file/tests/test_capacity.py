"""Tests for parse_capacity — human-friendly byte size parser."""

import pytest
from oaknut.file.capacity import parse_capacity


class TestBareNumbers:
    def test_plain_integer(self):
        assert parse_capacity("10485760") == 10485760

    def test_zero(self):
        assert parse_capacity("0") == 0


class TestBSuffix:
    def test_b_suffix(self):
        assert parse_capacity("1024B") == 1024

    def test_b_lowercase(self):
        assert parse_capacity("1024b") == 1024

    def test_space_before_suffix(self):
        assert parse_capacity("1024 B") == 1024


class TestKiloByteSuffixes:
    def test_kb(self):
        assert parse_capacity("100kB") == 100_000

    def test_kb_lowercase(self):
        assert parse_capacity("100kb") == 100_000

    def test_kb_uppercase(self):
        assert parse_capacity("100KB") == 100_000

    def test_kib(self):
        assert parse_capacity("100KiB") == 102_400

    def test_kib_case_insensitive(self):
        assert parse_capacity("100kib") == 102_400


class TestMegaByteSuffixes:
    def test_mb(self):
        assert parse_capacity("10MB") == 10_000_000

    def test_mb_lowercase(self):
        assert parse_capacity("10mb") == 10_000_000

    def test_mib(self):
        assert parse_capacity("10MiB") == 10 * 1024 * 1024

    def test_mib_case_insensitive(self):
        assert parse_capacity("10mib") == 10 * 1024 * 1024


class TestGigaByteSuffixes:
    def test_gb(self):
        assert parse_capacity("1GB") == 1_000_000_000

    def test_gib(self):
        assert parse_capacity("1GiB") == 1024 * 1024 * 1024


class TestEdgeCases:
    def test_whitespace_stripped(self):
        assert parse_capacity("  10 MB  ") == 10_000_000

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="cannot parse"):
            parse_capacity("-1")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_capacity("")

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            parse_capacity("foobar")

    def test_unknown_suffix_raises(self):
        with pytest.raises(ValueError, match="suffix"):
            parse_capacity("10XB")

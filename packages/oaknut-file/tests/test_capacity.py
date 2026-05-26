"""Tests for parse_capacity — human-friendly byte size parser."""

import pytest
from oaknut.file.capacity import format_capacity, parse_capacity


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


class TestFormatCapacity:
    """format_capacity is the human-facing inverse of parse_capacity.

    It renders IEC binary units (KiB/MiB/GiB), matching the
    power-of-two sizes of Acorn discs and quotas.
    """

    def test_zero_bytes(self):
        assert format_capacity(0) == "0 bytes"

    def test_one_byte_is_singular(self):
        assert format_capacity(1) == "1 byte"

    def test_small_byte_count(self):
        assert format_capacity(512) == "512 bytes"

    def test_just_below_a_kibibyte_stays_in_bytes(self):
        assert format_capacity(1023) == "1023 bytes"

    def test_exact_kibibyte(self):
        assert format_capacity(1024) == "1.0 KiB"

    def test_fractional_kibibyte(self):
        assert format_capacity(1536) == "1.5 KiB"

    def test_exact_mebibyte(self):
        # 0x00100000 — the AFS quota the disc afs-users complaint was about.
        assert format_capacity(1024 * 1024) == "1.0 MiB"

    def test_exact_gibibyte(self):
        assert format_capacity(1024 * 1024 * 1024) == "1.0 GiB"

    def test_rolls_up_to_largest_fitting_unit(self):
        # 2 MiB must read as MiB, not 2048 KiB.
        assert format_capacity(2 * 1024 * 1024) == "2.0 MiB"

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            format_capacity(-1)

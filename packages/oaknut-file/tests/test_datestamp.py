"""Tests for the RISC OS load/exec datestamp codec."""

from __future__ import annotations

from datetime import datetime

import pytest
from oaknut.file.datestamp import (
    RISCOS_EPOCH,
    decode_datestamp,
    encode_datestamp,
    is_datestamped,
)
from oaknut.file.exceptions import DatestampRangeError

#: Top 12 bits of the load address are 0xFFF on a typed+dated file.
_MARKER = 0xFFF00000


def _load(filetype: int, high_byte: int) -> int:
    return _MARKER | ((filetype & 0xFFF) << 8) | (high_byte & 0xFF)


class TestIsDatestamped:
    def test_marker_present(self):
        assert is_datestamped(_load(0xFFD, 0x00))

    def test_marker_absent(self):
        # A real load address (BBC default &1900) is not stamped.
        assert not is_datestamped(0x00001900)
        assert not is_datestamped(0xFFE00000)  # only 11 of the top 12 bits


class TestDecode:
    def test_unstamped_returns_none(self):
        assert decode_datestamp(0x00001900, 0x00008023) is None

    def test_epoch(self):
        # All date bits zero -> 1900-01-01 00:00:00.
        assert decode_datestamp(_load(0xFFF, 0x00), 0x00000000) == RISCOS_EPOCH

    def test_one_centisecond(self):
        got = decode_datestamp(_load(0xFFF, 0x00), 0x00000001)
        assert got == datetime(1900, 1, 1, 0, 0, 0, 10_000)

    def test_filetype_bits_do_not_affect_date(self):
        a = decode_datestamp(_load(0xFFF, 0x12), 0x3456789A)
        b = decode_datestamp(_load(0x000, 0x12), 0x3456789A)
        assert a == b


class TestRoundTrip:
    @pytest.mark.parametrize(
        "when",
        [
            datetime(1900, 1, 1, 0, 0, 0),
            datetime(1981, 7, 15, 9, 30, 0),
            datetime(2024, 3, 1, 14, 22, 8, 50_000),  # centisecond-aligned
            datetime(2087, 12, 31, 23, 59, 59, 990_000),
        ],
    )
    def test_encode_decode_identity(self, when):
        high, exec_word = encode_datestamp(when)
        assert decode_datestamp(_load(0xABC, high), exec_word) == when

    def test_sub_centisecond_truncates(self):
        # 3.456 ms of extra resolution the field cannot hold is dropped.
        high, exec_word = encode_datestamp(datetime(2024, 3, 1, 0, 0, 0, 53_456))
        assert decode_datestamp(_load(0xFFF, high), exec_word) == datetime(
            2024, 3, 1, 0, 0, 0, 50_000
        )


class TestRange:
    def test_before_epoch_raises(self):
        with pytest.raises(DatestampRangeError):
            encode_datestamp(datetime(1899, 12, 31, 23, 59, 59))

    def test_beyond_40_bits_raises(self):
        # The 40-bit centisecond field overflows in the 23rd century.
        with pytest.raises(DatestampRangeError):
            encode_datestamp(datetime(2300, 1, 1, 0, 0, 0))

"""IBM FM/MFM half-cell encoding and the CRC-CCITT used by address marks."""

from __future__ import annotations

import random

import pytest
from oaknut.hfe.ibm import (
    FM_DATA_MARK,
    FM_DELETED_DATA_MARK,
    FM_ID_MARK,
    MFM_SYNC,
    crc16,
    decode_byte,
    decode_bytes,
    fm_encode,
    mfm_encode,
)


class TestCRC:
    def test_check_value_for_ascii_digits(self):
        # The published check value of CRC-16/CCITT-FALSE.
        assert crc16(b"123456789") == 0x29B1

    def test_mfm_sync_preset(self):
        # Three A1 sync bytes take the 0xFFFF preset to 0xCDB4.
        assert crc16(b"\xa1\xa1\xa1") == 0xCDB4

    def test_continues_from_given_value(self):
        assert crc16(b"6789", crc16(b"12345")) == crc16(b"123456789")


class TestFM:
    def test_ordinary_byte_has_every_clock(self):
        assert fm_encode(b"\x00") == "1010101010101010"
        assert fm_encode(b"\xff") == "1111111111111111"

    def test_id_mark_uses_c7_clock(self):
        assert FM_ID_MARK == "1111010101111110"

    def test_data_marks(self):
        assert FM_DATA_MARK == "1111010101101111"
        assert FM_DELETED_DATA_MARK == "1111010101101010"


class TestMFM:
    def test_clock_only_between_zero_bits(self):
        # 0x00 after a 0 bit: every clock set.
        assert mfm_encode(b"\x00") == "1010101010101010"
        # 0xFF: no clocks at all.
        assert mfm_encode(b"\xff") == "0101010101010101"

    def test_first_clock_depends_on_previous_bit(self):
        assert mfm_encode(b"\x00", previous_bit=1) == "0010101010101010"

    def test_sync_word_is_a1_with_a_missing_clock(self):
        assert MFM_SYNC == f"{0x4489:016b}"
        assert decode_byte(MFM_SYNC) == 0xA1
        assert mfm_encode(b"\xa1") != MFM_SYNC


_SAMPLES = [bytes(range(256))] + [random.Random(seed).randbytes(64) for seed in range(16)]


@pytest.mark.parametrize("encode", [fm_encode, mfm_encode])
@pytest.mark.parametrize("data", _SAMPLES)
def test_decode_inverts_encode(encode, data):
    cells = encode(data)
    assert bytes(decode_byte(cells[i : i + 16]) for i in range(0, len(cells), 16)) == data
    assert decode_bytes(cells, 0, len(data)) == data


def test_decode_bytes_pads_a_short_tail_with_zeros():
    assert decode_bytes(fm_encode(b"\xff")[:8], 0, 1) == b"\xf0"

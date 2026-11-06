"""The HFE container: header, track table, side interleave and v3 opcodes."""

from __future__ import annotations

import struct

import pytest
from oaknut.hfe.container import (
    HFEFormatError,
    HFEImage,
    TrackEncoding,
    write_hfe,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

HFE_DIRPATH = REFERENCE_IMAGES_DIRPATH / "hfe"
DUNJUNZ_S1_FILEPATH = HFE_DIRPATH / "Dunjunz_D1S1_40T_HG3_8518BF40_1.hfe"
CITADEL_FILEPATH = HFE_DIRPATH / "Citadel_FSD0174_1.hfe"


def _reverse(byte: int) -> int:
    return int(f"{byte:08b}"[::-1], 2)


def _hand_built_v3(side0: bytes, side1: bytes = b"") -> bytes:
    """A one-track v3 image from raw (already bit-reversed) side bytes."""
    num_sides = 2 if side1 else 1
    side_len = max(len(side0), len(side1))
    side0 = side0.ljust(side_len, b"\x00")
    side1 = side1.ljust(side_len, b"\x00")
    header = bytearray(b"\xff" * 512)
    header[0:8] = b"HXCHFEV3"
    header[8:12] = bytes([0, 1, num_sides, 2])
    struct.pack_into("<HHBBH", header, 12, 250, 300, 7, 0xFF, 1)
    lut = bytearray(b"\xff" * 512)
    struct.pack_into("<HH", lut, 0, 2, side_len * 2)
    track = bytearray()
    for offset in range(0, side_len, 256):
        track += side0[offset : offset + 256].ljust(256, b"\x00")
        track += side1[offset : offset + 256].ljust(256, b"\x00")
    return bytes(header + lut + track)


class TestHeader:
    def test_dunjunz_header(self):
        image = HFEImage.from_filepath(DUNJUNZ_S1_FILEPATH)
        header = image.header
        assert header.version == 3
        assert header.num_tracks == 41
        assert header.num_sides == 1
        assert header.track_encoding is TrackEncoding.ISOIBM_FM
        assert header.bitrate_kbps == 250
        assert header.rpm == 300
        assert header.interface_mode == 7

    def test_citadel_has_eighty_tracks(self):
        image = HFEImage.from_filepath(CITADEL_FILEPATH)
        assert image.header.num_tracks == 80

    def test_unknown_track_encoding_is_kept_as_an_int(self):
        data = bytearray(_hand_built_v3(b"\x55"))
        data[11] = 0x42
        assert HFEImage.from_bytes(bytes(data)).header.track_encoding == 0x42

    @pytest.mark.parametrize(
        "mutate, message",
        [
            (lambda d: d.__setitem__(slice(0, 8), b"NOTANHFE"), "signature"),
            (lambda d: d.__setitem__(8, 1), "revision"),
            (lambda d: d.__setitem__(10, 0), "side"),
            (lambda d: d.__setitem__(10, 3), "side"),
            (lambda d: d.__setitem__(9, 0), "track"),
            (lambda d: struct.pack_into("<H", d, 18, 99), "track list"),
        ],
    )
    def test_malformed_headers_are_rejected(self, mutate, message):
        data = bytearray(_hand_built_v3(b"\x55"))
        mutate(data)
        with pytest.raises(HFEFormatError, match=message):
            HFEImage.from_bytes(bytes(data))

    def test_too_short_to_hold_a_header(self):
        with pytest.raises(HFEFormatError, match="too short"):
            HFEImage.from_bytes(b"HXCHFEV3")

    def test_track_data_beyond_end_of_file(self):
        data = _hand_built_v3(b"\x55" * 600)[:-500]
        image = HFEImage.from_bytes(data)
        with pytest.raises(HFEFormatError, match="beyond the end"):
            image.track(0, 0)

    def test_track_and_side_out_of_range(self):
        image = HFEImage.from_bytes(_hand_built_v3(b"\x55"))
        with pytest.raises(IndexError):
            image.track(1, 0)
        with pytest.raises(IndexError):
            image.track(0, 1)


class TestSamples:
    def test_bytes_are_stored_least_significant_bit_first(self):
        image = HFEImage.from_bytes(_hand_built_v3(bytes([_reverse(0b10010000)])))
        assert image.track(0, 0).samples == "10010000"

    def test_sides_interleave_in_256_byte_halves_of_each_block(self):
        side0 = bytes([_reverse(0x80)]) * 300
        side1 = bytes([_reverse(0x01)]) * 300
        image = HFEImage.from_bytes(_hand_built_v3(side0, side1))
        assert image.track(0, 0).samples == "10000000" * 300
        assert image.track(0, 1).samples == "00000001" * 300

    def test_v3_nop_and_setindex_add_no_samples(self):
        raw = bytes([_reverse(0xF0), _reverse(0xF1), _reverse(0xAA)])
        track = HFEImage.from_bytes(_hand_built_v3(raw)).track(0, 0)
        assert track.samples == "10101010"
        assert track.index_positions == (0,)

    def test_v3_setbitrate_records_the_rate(self):
        # 36 MHz / (2 * 72) = 250 kbit/s.
        raw = bytes([_reverse(0xF2), _reverse(72), _reverse(0xAA)])
        track = HFEImage.from_bytes(_hand_built_v3(raw)).track(0, 0)
        assert track.samples == "10101010"
        assert track.bitrates_kbps == (250,)

    def test_v3_skipbits_discards_leading_bits_of_the_next_byte(self):
        raw = bytes([_reverse(0xF3), _reverse(3), _reverse(0b11100101)])
        assert HFEImage.from_bytes(_hand_built_v3(raw)).track(0, 0).samples == "00101"

    def test_v3_rand_is_eight_weak_samples(self):
        raw = bytes([_reverse(0xAA), _reverse(0xF4), _reverse(0xAA)])
        track = HFEImage.from_bytes(_hand_built_v3(raw)).track(0, 0)
        assert track.samples == "10101010" + "00000000" + "10101010"
        assert track.weak_samples == 8

    def test_v1_has_no_opcodes(self):
        data = bytearray(_hand_built_v3(bytes([_reverse(0xF4)])))
        data[0:8] = b"HXCPICFE"
        assert HFEImage.from_bytes(bytes(data)).track(0, 0).samples == "11110100"

    def test_citadel_unformatted_tracks_are_all_weak(self):
        track = HFEImage.from_filepath(CITADEL_FILEPATH).track(60, 0)
        assert track.weak_samples > 0.99 * len(track.samples)


class TestWrite:
    @pytest.mark.parametrize("version", [1, 3])
    def test_round_trip(self, version):
        tracks = [
            ["10" * 4000, "01" * 4000 + "1"],
            ["1100" * 3000, "0011" * 3000],
        ]
        data = write_hfe(tracks, version=version, track_encoding=TrackEncoding.ISOIBM_MFM)
        image = HFEImage.from_bytes(data)
        assert image.header.version == version
        assert image.header.num_tracks == 2
        assert image.header.num_sides == 2
        assert image.header.track_encoding is TrackEncoding.ISOIBM_MFM
        for track_index, sides in enumerate(tracks):
            for side_index, samples in enumerate(sides):
                read = image.track(track_index, side_index).samples
                # Writing pads a side to whole bytes, and both sides of a
                # track to the same length, with zero samples.
                assert read.rstrip("0").startswith(samples.rstrip("0"))
                assert set(read[len(samples) :]) <= {"0"}

    def test_weak_samples_are_written_as_rand(self):
        data = write_hfe([["10101010" + "????????" + "10101010"]])
        track = HFEImage.from_bytes(data).track(0, 0)
        assert track.weak_samples == 8

    def test_weak_samples_need_v3(self):
        with pytest.raises(ValueError, match="v3"):
            write_hfe([["????????"]], version=1)

    def test_v3_rejects_samples_that_read_as_an_opcode(self):
        with pytest.raises(ValueError, match="opcode"):
            write_hfe([["11110000"]])

    def test_sides_must_agree(self):
        with pytest.raises(ValueError, match="side"):
            write_hfe([["10"], ["10", "10"]])

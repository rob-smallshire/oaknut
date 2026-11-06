"""Flattening a decoded disc into a logical sector image."""

from __future__ import annotations

import pytest
from oaknut.hfe.build import (
    TRACK_SAMPLES_300RPM_250KBPS,
    FormattedSector,
    build_track,
    track_samples,
)
from oaknut.hfe.container import HFEImage, write_hfe
from oaknut.hfe.decode import Encoding, SectorID, decode_image
from oaknut.hfe.flat import flatten, flatten_hfe

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

HFE_DIRPATH = REFERENCE_IMAGES_DIRPATH / "hfe"


def _payload(track: int, side: int, record: int, size: int = 256) -> bytes:
    return bytes([track, side, record]) + bytes(size - 3)


def _track(sectors, encoding=Encoding.FM) -> str:
    half_cells = TRACK_SAMPLES_300RPM_250KBPS // (2 if encoding is Encoding.FM else 1)
    return track_samples(build_track(sectors, encoding, half_cells=half_cells), encoding)


def _standard(track, side, records=range(10), encoding=Encoding.FM, cylinder=None, size_code=1):
    return _track(
        [
            FormattedSector(
                SectorID(track if cylinder is None else cylinder, side, record, size_code),
                _payload(track, side, record, 128 << size_code),
            )
            for record in records
        ],
        encoding,
    )


def _disc(tracks, **kwargs):
    return decode_image(HFEImage.from_bytes(write_hfe(tracks, **kwargs)))


class TestGolden:
    @pytest.mark.parametrize(
        "stem",
        ["Dunjunz_D1S1_40T_HG3_8518BF40_1", "Dunjunz_D1S2_40T_HG3_54F4B47A_1"],
    )
    def test_dunjunz_matches_the_8271_read(self, stem):
        flat = flatten_hfe(HFE_DIRPATH / f"{stem}.hfe")
        assert flat.data == (HFE_DIRPATH / f"{stem}.ssd").read_bytes()
        assert flat.suffix == ".ssd"
        assert flat.layout.num_tracks == 40
        assert flat.missing == ()

    def test_citadel_unformatted_tail_is_dropped(self):
        flat = flatten_hfe(HFE_DIRPATH / "Citadel_FSD0174_1.hfe")
        assert flat.layout.num_tracks == 40
        assert len(flat.data) == 40 * 10 * 256
        assert flat.data[0:8] == b"SUPERIOR"


class TestLayout:
    def test_single_sided_fm(self):
        flat = flatten(_disc([[_standard(t, 0)] for t in range(3)]))
        layout = flat.layout
        assert (layout.encoding, layout.num_tracks, layout.num_sides) == (Encoding.FM, 3, 1)
        assert (layout.sectors_per_track, layout.sector_size, layout.first_record) == (10, 256, 0)
        assert flat.data[2 * 2560 + 5 * 256 : 2 * 2560 + 5 * 256 + 3] == bytes([2, 0, 5])
        assert flat.suffix == ".ssd"

    def test_double_sided_interleaves_tracks(self):
        flat = flatten(_disc([[_standard(t, 0), _standard(t, 1)] for t in range(2)]))
        assert flat.layout.num_sides == 2
        offsets = {(t, s): (t * 2 + s) * 2560 for t in range(2) for s in range(2)}
        for (track, side), offset in offsets.items():
            assert flat.data[offset : offset + 3] == bytes([track, side, 0])
        assert flat.suffix == ".dsd"

    def test_a_blank_second_side_is_dropped(self):
        blank = "0" * TRACK_SAMPLES_300RPM_250KBPS
        flat = flatten(_disc([[_standard(t, 0), blank] for t in range(2)]))
        assert flat.layout.num_sides == 1
        assert flat.suffix == ".ssd"

    def test_skewed_sector_order_is_put_in_record_order(self):
        flat = flatten(_disc([[_standard(0, 0, records=[3, 4, 5, 6, 7, 8, 9, 0, 1, 2])]]))
        assert [flat.data[r * 256 + 2] for r in range(10)] == list(range(10))

    def test_adfs_mfm(self):
        tracks = [
            [_standard(t, s, records=range(16), encoding=Encoding.MFM) for s in range(2)]
            for t in range(2)
        ]
        flat = flatten(_disc(tracks))
        assert flat.layout.encoding is Encoding.MFM
        assert flat.layout.sectors_per_track == 16
        assert flat.suffix == ".adl"

    def test_records_numbered_from_one(self):
        flat = flatten(_disc([[_standard(0, 0, records=range(1, 11))]]))
        assert flat.layout.first_record == 1
        assert flat.data[2] == 1

    def test_large_sectors(self):
        tracks = [[_standard(0, 0, records=range(5), encoding=Encoding.MFM, size_code=3)]]
        flat = flatten(_disc(tracks))
        assert (flat.layout.sector_size, flat.layout.sectors_per_track) == (1024, 5)
        assert flat.suffix == ".adf"

    def test_double_stepped_capture(self):
        # A 40-track disc read in an 80-track drive: each logical track
        # appears on two physical tracks.
        tracks = [[_standard(p, 0, cylinder=p // 2)] for p in range(6)]
        flat = flatten(_disc(tracks))
        assert flat.layout.num_tracks == 3
        assert flat.layout.double_stepped
        assert flat.data[2 * 2560 : 2 * 2560 + 3] == bytes([4, 0, 0])


class TestDefects:
    def test_unreadable_sectors_are_filled_and_reported(self):
        sectors = [
            FormattedSector(SectorID(0, 0, r, 1), b"\xaa" * 256, bad_data_crc=(r == 4))
            for r in range(10)
        ]
        flat = flatten(_disc([[_track(sectors)]]), fill=0x00)
        assert flat.missing == ((0, 0, 4),)
        assert flat.data[4 * 256 : 5 * 256] == bytes(256)
        assert flat.data[3 * 256 : 4 * 256] == b"\xaa" * 256

    def test_a_good_duplicate_wins_over_a_bad_one(self):
        # Eleven FM sectors do not fit a track, so use nine plus a duplicate.
        sectors = [FormattedSector(SectorID(0, 0, r, 1), b"ok") for r in range(9)]
        sectors.insert(0, FormattedSector(SectorID(0, 0, 0, 1), b"bad", bad_data_crc=True))
        flat = flatten(_disc([[_track(sectors)]]))
        assert flat.data[:2] == b"ok"
        assert flat.missing == ()

    def test_sectors_claiming_another_cylinder_are_excluded(self):
        sectors = [FormattedSector(SectorID(1, 0, r, 1), b"ok") for r in range(9)]
        sectors.append(FormattedSector(SectorID(17, 0, 9, 1), b"decoy"))
        flat = flatten(_disc([[_standard(0, 0)], [_track(sectors)]]))
        assert flat.missing == ((1, 0, 9),)

    def test_a_missing_track_in_the_middle(self):
        blank = "0" * TRACK_SAMPLES_300RPM_250KBPS
        flat = flatten(_disc([[_standard(0, 0)], [blank], [_standard(2, 0)]]))
        assert flat.layout.num_tracks == 3
        assert len(flat.missing) == 10
        assert {(t, s) for t, s, _ in flat.missing} == {(1, 0)}

    def test_nothing_decodable(self):
        blank = "0" * TRACK_SAMPLES_300RPM_250KBPS
        flat = flatten(_disc([[blank]]))
        assert flat.data == b""
        assert flat.layout is None
        assert flat.suffix is None

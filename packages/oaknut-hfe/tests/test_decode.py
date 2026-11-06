"""Decoding FM and MFM tracks into sectors."""

from __future__ import annotations

import pytest
from oaknut.hfe.build import (
    TRACK_SAMPLES_300RPM_250KBPS,
    FormattedSector,
    build_track,
    track_samples,
)
from oaknut.hfe.container import HFEImage, write_hfe
from oaknut.hfe.decode import (
    DataMark,
    Encoding,
    SectorID,
    decode_image,
    decode_track,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

HFE_DIRPATH = REFERENCE_IMAGES_DIRPATH / "hfe"
DUNJUNZ_S1_FILEPATH = HFE_DIRPATH / "Dunjunz_D1S1_40T_HG3_8518BF40_1.hfe"

FM_HALF_CELLS = TRACK_SAMPLES_300RPM_250KBPS // 2
MFM_HALF_CELLS = TRACK_SAMPLES_300RPM_250KBPS


def _payload(track: int, record: int, size: int = 256) -> bytes:
    return bytes((track * 31 + record * 7 + i) & 0xFF for i in range(size))


def _dfs_sectors(track: int = 0, count: int = 10) -> list[FormattedSector]:
    return [
        FormattedSector(SectorID(track, 0, record, 1), _payload(track, record))
        for record in range(count)
    ]


def _fm_samples(sectors) -> str:
    cells = build_track(sectors, Encoding.FM, half_cells=FM_HALF_CELLS)
    return track_samples(cells, Encoding.FM)


def _mfm_samples(sectors) -> str:
    cells = build_track(sectors, Encoding.MFM, half_cells=MFM_HALF_CELLS)
    return track_samples(cells, Encoding.MFM)


class TestFM:
    def test_clean_dfs_track(self):
        sectors = decode_track(_fm_samples(_dfs_sectors(track=5)))
        assert [s.id for s in sectors] == [SectorID(5, 0, r, 1) for r in range(10)]
        assert all(s.encoding is Encoding.FM for s in sectors)
        assert all(s.readable for s in sectors)
        assert [s.data for s in sectors] == [_payload(5, r) for r in range(10)]
        positions = [s.position for s in sectors]
        assert positions == sorted(positions)

    def test_any_bit_offset(self):
        samples = _fm_samples(_dfs_sectors())
        for shift in range(1, 5):
            sectors = decode_track("0" * shift + samples[:-shift])
            assert len(sectors) == 10
            assert all(s.readable for s in sectors)

    def test_tolerates_a_one_sample_slip_mid_track(self):
        samples = _fm_samples(_dfs_sectors())
        # Inside sector 5's data field, every later transition arrives one
        # sample late: only the other sampling phase still reads it.
        slip = decode_track(samples)[5].position + 2 * 16 * 40
        slipped = samples[:slip] + "0" + samples[slip:-1]
        sectors = decode_track(slipped)
        assert len(sectors) == 10
        assert all(s.readable for s in sectors)

    def test_sector_spanning_the_index(self):
        samples = _fm_samples(_dfs_sectors())
        # Rotate so that the index falls in the middle of sector 0's data.
        first = decode_track(samples)[0]
        cut = first.position + 2 * 16 * 60
        sectors = decode_track(samples[cut:] + samples[:cut])
        assert sorted(s.id.record for s in sectors) == list(range(10))
        assert all(s.readable for s in sectors)

    def test_bad_id_crc(self):
        sectors = _dfs_sectors()
        sectors[3] = FormattedSector(SectorID(0, 0, 3, 1), b"x", bad_id_crc=True)
        decoded = decode_track(_fm_samples(sectors))
        assert not decoded[3].id_crc_ok
        assert decoded[3].data_crc_ok
        assert not decoded[3].readable

    def test_bad_data_crc(self):
        sectors = _dfs_sectors()
        sectors[4] = FormattedSector(SectorID(0, 0, 4, 1), b"x", bad_data_crc=True)
        decoded = decode_track(_fm_samples(sectors))
        assert decoded[4].id_crc_ok
        assert decoded[4].data_crc_ok is False
        assert decoded[4].data.startswith(b"x")

    def test_deleted_data_mark(self):
        sectors = _dfs_sectors()
        sectors[2] = FormattedSector(SectorID(0, 0, 2, 1), b"gone", deleted=True)
        decoded = decode_track(_fm_samples(sectors))
        assert decoded[2].data_mark is DataMark.DELETED
        assert decoded[2].data.startswith(b"gone")
        assert decoded[1].data_mark is DataMark.NORMAL

    def test_missing_data_field(self):
        sectors = _dfs_sectors()
        sectors[7] = FormattedSector(SectorID(0, 0, 7, 1), omit_data=True)
        decoded = decode_track(_fm_samples(sectors))
        assert decoded[7].data_mark is None
        assert decoded[7].data is None
        assert decoded[7].data_crc_ok is None
        assert decoded[8].readable

    def test_duplicate_and_out_of_range_ids(self):
        sectors = [
            FormattedSector(SectorID(0, 0, 1, 1), b"first"),
            FormattedSector(SectorID(0, 0, 1, 1), b"second"),
            FormattedSector(SectorID(99, 7, 200, 1), b"odd"),
        ]
        decoded = decode_track(_fm_samples(sectors))
        assert [s.id for s in decoded] == [s.id for s in sectors]
        assert [s.data[:6].rstrip(b"\0") for s in decoded] == [b"first", b"second", b"odd"]

    @pytest.mark.parametrize("size_code, size", [(0, 128), (2, 512), (3, 1024), (4, 2048)])
    def test_sector_sizes(self, size_code, size):
        sectors = [FormattedSector(SectorID(0, 0, 0, size_code), _payload(0, 0, size))]
        (decoded,) = decode_track(_fm_samples(sectors))
        assert decoded.id.size(Encoding.FM) == size
        assert decoded.data == _payload(0, 0, size)
        assert decoded.readable

    def test_weak_region_hides_sectors(self):
        samples = _fm_samples(_dfs_sectors())
        clean = decode_track(samples)
        start = clean[4].position - 64
        end = clean[6].position - 64
        # Weak samples read as zeros, as the container delivers them.
        weakened = samples[:start] + "0" * (end - start) + samples[end:]
        assert [s.id.record for s in decode_track(weakened)] == [0, 1, 2, 3, 6, 7, 8, 9]

    def test_unformatted_track(self):
        assert decode_track("0" * TRACK_SAMPLES_300RPM_250KBPS) == ()


class TestMFM:
    def test_clean_adfs_track(self):
        sectors = [FormattedSector(SectorID(3, 1, r, 1), _payload(3, r)) for r in range(16)]
        decoded = decode_track(_mfm_samples(sectors))
        assert [s.id for s in decoded] == [s.id for s in sectors]
        assert all(s.encoding is Encoding.MFM for s in decoded)
        assert all(s.readable for s in decoded)
        assert [s.data for s in decoded] == [_payload(3, r) for r in range(16)]

    def test_size_code_uses_the_low_two_bits(self):
        assert SectorID(0, 0, 0, 5).size(Encoding.MFM) == 256
        assert SectorID(0, 0, 0, 5).size(Encoding.FM) == 4096

    def test_any_bit_offset(self):
        samples = _mfm_samples(_dfs_sectors(count=16))
        decoded = decode_track("000" + samples[:-3])
        assert len(decoded) == 16
        assert all(s.readable for s in decoded)

    def test_bad_crcs_and_deleted(self):
        sectors = _dfs_sectors(count=5)
        sectors[0] = FormattedSector(SectorID(0, 0, 0, 1), b"a", bad_id_crc=True)
        sectors[1] = FormattedSector(SectorID(0, 0, 1, 1), b"b", bad_data_crc=True)
        sectors[2] = FormattedSector(SectorID(0, 0, 2, 1), b"c", deleted=True)
        decoded = decode_track(_mfm_samples(sectors))
        assert not decoded[0].id_crc_ok
        assert decoded[1].data_crc_ok is False
        assert decoded[2].data_mark is DataMark.DELETED
        assert decoded[2].data_crc_ok


def test_mixed_density_track():
    fm = track_samples(build_track(_dfs_sectors(count=4), Encoding.FM), Encoding.FM)
    mfm = track_samples(
        build_track([FormattedSector(SectorID(0, 0, 9, 1), b"mfm")], Encoding.MFM),
        Encoding.MFM,
    )
    decoded = decode_track(fm + mfm + "0" * 4000)
    assert [(s.encoding, s.id.record) for s in decoded] == [
        (Encoding.FM, 0),
        (Encoding.FM, 1),
        (Encoding.FM, 2),
        (Encoding.FM, 3),
        (Encoding.MFM, 9),
    ]


def test_decode_image_from_built_hfe():
    tracks = [[_fm_samples(_dfs_sectors(track=t))] for t in range(3)]
    disc = decode_image(HFEImage.from_bytes(write_hfe(tracks)))
    assert len(disc.tracks) == 3
    track = disc.track(2, 0)
    assert (track.track, track.side) == (2, 0)
    assert [s.id for s in track.sectors] == [SectorID(2, 0, r, 1) for r in range(10)]


@pytest.fixture(scope="module")
def dunjunz_disc():
    return decode_image(HFEImage.from_filepath(DUNJUNZ_S1_FILEPATH))


class TestDunjunz:
    def test_every_formatted_track_has_ten_good_sectors(self, dunjunz_disc):
        for track in range(40):
            sectors = dunjunz_disc.track(track, 0).sectors
            assert sorted(s.id.record for s in sectors) == list(range(10)), track
            assert all(s.readable for s in sectors), track
            assert {s.id.cylinder for s in sectors} == {track}
            assert {s.data_mark for s in sectors} == {DataMark.NORMAL}

    def test_track_forty_is_unformatted(self, dunjunz_disc):
        assert dunjunz_disc.track(40, 0).sectors == ()

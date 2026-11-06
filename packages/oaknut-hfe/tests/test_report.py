"""The sector-level report: what makes each track and sector non-standard."""

from __future__ import annotations

from oaknut.hfe.build import (
    TRACK_SAMPLES_300RPM_250KBPS,
    FormattedSector,
    build_track,
    track_samples,
)
from oaknut.hfe.container import HFEImage, write_hfe
from oaknut.hfe.decode import Encoding, SectorID, decode_image
from oaknut.hfe.flat import flatten
from oaknut.hfe.report import analyse

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

HFE_DIRPATH = REFERENCE_IMAGES_DIRPATH / "hfe"
BLANK = "0" * TRACK_SAMPLES_300RPM_250KBPS


def _fm(sectors) -> str:
    cells = build_track(sectors, Encoding.FM, half_cells=TRACK_SAMPLES_300RPM_250KBPS // 2)
    return track_samples(cells, Encoding.FM)


def _standard(track, records=range(10)):
    return _fm([FormattedSector(SectorID(track, 0, r, 1), b"d") for r in records])


def _findings(tracks):
    disc = decode_image(HFEImage.from_bytes(write_hfe([[t] for t in tracks])))
    return analyse(disc, flatten(disc).layout)


def test_a_standard_disc_has_no_remarks():
    findings = _findings([_standard(0), _standard(1)])
    assert [f.remarks for f in findings] == [(), ()]
    assert all(s.remarks == () for f in findings for s in f.sectors)
    assert not any(f.anomalous for f in findings)


def test_unformatted_track():
    findings = _findings([_standard(0), BLANK])
    assert findings[1].remarks == ("unformatted",)


def test_track_beyond_the_layout():
    findings = _findings([_standard(0), BLANK, _standard(2, records=[0])])
    # Track 2 holds a standard sector, so the layout runs to it.
    assert "1 of 10 sectors" in findings[2].remarks
    assert findings[2].anomalous


def test_missing_records_are_listed():
    findings = _findings([_standard(0), _standard(1, records=[0, 1, 2, 5, 6, 7, 8, 9])])
    assert "8 of 10 sectors" in findings[1].remarks
    assert "missing records 3, 4" in findings[1].remarks


def test_sector_remarks():
    sectors = [
        FormattedSector(SectorID(1, 0, 0, 1), b"a", bad_id_crc=True),
        FormattedSector(SectorID(1, 0, 1, 1), b"b", bad_data_crc=True),
        FormattedSector(SectorID(1, 0, 2, 1), b"c", deleted=True),
        FormattedSector(SectorID(1, 0, 3, 1), omit_data=True),
        FormattedSector(SectorID(9, 0, 4, 1), b"e"),
        FormattedSector(SectorID(1, 1, 5, 1), b"f"),
        FormattedSector(SectorID(1, 0, 42, 1), b"g"),
        FormattedSector(SectorID(1, 0, 6, 0), b"h"),
        FormattedSector(SectorID(1, 0, 7, 1), b"i"),
        FormattedSector(SectorID(1, 0, 7, 1), b"j"),
    ]
    findings = _findings([_standard(0), _fm(sectors)])
    remarks = [s.remarks for s in findings[1].sectors]
    assert remarks == [
        ("ID CRC error",),
        ("data CRC error",),
        ("deleted data",),
        ("no data field",),
        ("cylinder 9 on track 1",),
        ("head 1 on side 0",),
        ("record 42 outside 0-9",),
        ("128-byte sector",),
        ("duplicate ID",),
        ("duplicate ID",),
    ]
    assert findings[1].anomalous


def test_weak_samples_are_remarked():
    samples = _standard(0)
    weak = samples[:-800] + "?" * 800
    disc = decode_image(HFEImage.from_bytes(write_hfe([[weak]])))
    (finding,) = analyse(disc, flatten(disc).layout)
    assert "800 weak samples" in finding.remarks


def test_dunjunz_is_clean_apart_from_its_unformatted_last_track():
    disc = decode_image(HFEImage.from_filepath(HFE_DIRPATH / "Dunjunz_D1S1_40T_HG3_8518BF40_1.hfe"))
    findings = analyse(disc, flatten(disc).layout)
    anomalous = [(f.track, f.remarks) for f in findings if f.anomalous]
    assert anomalous == [(40, ("unformatted",))]


def test_no_layout_at_all():
    disc = decode_image(HFEImage.from_bytes(write_hfe([[BLANK]])))
    (finding,) = analyse(disc, None)
    assert finding.remarks == ("unformatted",)

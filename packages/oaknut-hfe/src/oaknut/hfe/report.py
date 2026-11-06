"""What makes each track and sector of a decoded disc non-standard.

Copy protection works by putting things on a disc that a normal format
would not: IDs claiming another cylinder or head, records outside the
usual range, odd sector sizes, duplicate IDs, deliberate CRC errors,
deleted-data marks, missing data fields, weak bits, and tracks beyond
the formatted range. :func:`analyse` compares every decoded track and
sector with the disc's inferred :class:`~oaknut.hfe.flatten.SectorLayout`
and names each departure from it, so a protection scheme can be read
off the report.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from oaknut.hfe.decode import DataMark, DecodedDisc, DecodedSector, DecodedTrack
from oaknut.hfe.flatten import SectorLayout

__all__ = ["SectorFinding", "TrackFinding", "analyse"]


@dataclass(frozen=True)
class SectorFinding:
    """One decoded sector and how it departs from the layout."""

    sector: DecodedSector
    remarks: tuple[str, ...]


@dataclass(frozen=True)
class TrackFinding:
    """One physical track side and how it departs from the layout."""

    track: int
    side: int
    decoded: DecodedTrack
    sectors: tuple[SectorFinding, ...]
    remarks: tuple[str, ...]

    @property
    def anomalous(self) -> bool:
        """Whether the track or any of its sectors drew a remark."""
        return bool(self.remarks) or any(finding.remarks for finding in self.sectors)


def analyse(disc: DecodedDisc, layout: SectorLayout | None) -> tuple[TrackFinding, ...]:
    """Findings for every track of *disc* against *layout*.

    With no *layout* (nothing standard could be decoded) only the
    layout-independent remarks are made.
    """
    return tuple(_analyse_track(track, layout) for track in disc.tracks)


def _analyse_track(track: DecodedTrack, layout: SectorLayout | None) -> TrackFinding:
    step = 2 if layout is not None and layout.double_stepped else 1
    logical_track = track.track // step
    ids = Counter(sector.id for sector in track.sectors)
    sectors = tuple(
        SectorFinding(sector, _sector_remarks(sector, track, logical_track, layout, ids))
        for sector in track.sectors
    )

    remarks: list[str] = []
    if not track.sectors:
        remarks.append("unformatted")
    elif layout is not None:
        if track.track % step:
            remarks.append("between the tracks of a double-stepped disc")
        elif logical_track >= layout.num_tracks:
            remarks.append(f"beyond the layout's {layout.num_tracks} tracks")
        else:
            expected = range(layout.first_record, layout.first_record + layout.sectors_per_track)
            present = {
                sector.id.record
                for sector in track.sectors
                if sector.id.cylinder == logical_track and sector.id.record in expected
            }
            if len(present) != layout.sectors_per_track:
                remarks.append(f"{len(present)} of {layout.sectors_per_track} sectors")
                absent = [str(record) for record in expected if record not in present]
                remarks.append(f"missing records {', '.join(absent)}")
    if track.weak_samples:
        remarks.append(f"{track.weak_samples} weak samples")
    return TrackFinding(track.track, track.side, track, sectors, tuple(remarks))


def _sector_remarks(
    sector: DecodedSector,
    track: DecodedTrack,
    logical_track: int,
    layout: SectorLayout | None,
    ids: Counter,
) -> tuple[str, ...]:
    remarks: list[str] = []
    if not sector.id_crc_ok:
        remarks.append("ID CRC error")
    if sector.data_mark is None:
        remarks.append("no data field")
    else:
        if sector.data_crc_ok is False:
            remarks.append("data CRC error")
        if sector.data_mark is DataMark.DELETED:
            remarks.append("deleted data")
    if sector.id.cylinder != logical_track:
        remarks.append(f"cylinder {sector.id.cylinder} on track {track.track}")
    if sector.id.head != track.side:
        remarks.append(f"head {sector.id.head} on side {track.side}")
    if layout is not None:
        if sector.encoding is not layout.encoding:
            remarks.append(f"{sector.encoding.value} sector")
        last = layout.first_record + layout.sectors_per_track - 1
        if not layout.first_record <= sector.id.record <= last:
            remarks.append(f"record {sector.id.record} outside {layout.first_record}-{last}")
        size = sector.id.size(sector.encoding)
        if size != layout.sector_size:
            remarks.append(f"{size}-byte sector")
    if ids[sector.id] > 1:
        remarks.append("duplicate ID")
    return tuple(remarks)

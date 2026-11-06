"""Flatten a decoded disc into a logical sector image.

The filesystems read sector images: each track's sectors in record order,
tracks in order, the sides of a double-sided disc interleaved track by
track (the ``.dsd`` and ``.adl`` layout). Flattening chooses the disc's
*standard* sector layout from what was decoded and fills each slot of it
from the best read of that sector.

The layout is inferred, not taken from the HFE header:

* the dominant density and sector size among readable sectors;
* the usual number of sectors per track, and the first record number;
* whether the capture is *double-stepped* (a 40-track disc read in an
  80-track drive, so that each logical track occupies two physical
  tracks), from whether the ID fields' cylinder numbers run at half the
  physical track number;
* the number of tracks and sides that hold any standard sector.

A slot is filled from a readable sector on the matching physical track
whose ID has the slot's cylinder, record and size. Sectors that claim
another cylinder, a record outside the layout, or another size are left
out; they are visible in the sector report. A slot with no readable
sector is filled with *fill* bytes and listed in
:attr:`FlatImage.missing`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from oaknut.hfe.container import HFEImage
from oaknut.hfe.decode import DecodedDisc, DecodedSector, Encoding, decode_image

__all__ = ["SectorLayout", "FlatImage", "flatten", "flatten_hfe"]


@dataclass(frozen=True)
class SectorLayout:
    """The standard sector layout inferred for a disc."""

    encoding: Encoding
    sector_size: int
    sectors_per_track: int
    first_record: int
    num_tracks: int
    num_sides: int
    double_stepped: bool = False

    @property
    def track_size(self) -> int:
        return self.sector_size * self.sectors_per_track


@dataclass(frozen=True)
class FlatImage:
    """A logical sector image made from an HFE disc."""

    data: bytes
    #: ``None`` when no standard sector could be decoded at all.
    layout: SectorLayout | None
    #: ``(track, side, record)`` of each slot no readable sector filled.
    missing: tuple[tuple[int, int, int], ...] = ()
    #: The conventional extension for an image with this layout, if any.
    suffix: str | None = None


def flatten_hfe(filepath: Path, *, fill: int = 0x00) -> FlatImage:
    """Decode and flatten the HFE file at *filepath*."""
    return flatten(decode_image(HFEImage.from_filepath(filepath)), fill=fill)


def flatten(disc: DecodedDisc, *, fill: int = 0x00) -> FlatImage:
    """The logical sector image of *disc*, with unreadable slots *fill*-ed."""
    readable = [
        (track.track, track.side, sector)
        for track in disc.tracks
        for sector in track.sectors
        if sector.readable
    ]
    if not readable:
        return FlatImage(b"", None)

    (encoding, sector_size), _ = Counter(
        (s.encoding, len(s.data)) for _, _, s in readable
    ).most_common(1)[0]
    standard = [
        (track, side, s)
        for track, side, s in readable
        if s.encoding is encoding and len(s.data) == sector_size
    ]

    double_stepped = _double_stepped(standard)
    step = 2 if double_stepped else 1

    per_track: dict[tuple[int, int], set[int]] = {}
    for track, side, s in standard:
        if s.id.cylinder * step == track:
            per_track.setdefault((track // step, side), set()).add(s.id.record)
    if not per_track:
        return FlatImage(b"", None)
    sectors_per_track = Counter(len(records) for records in per_track.values()).most_common(1)[0][0]
    first_record = Counter(min(records) for records in per_track.values()).most_common(1)[0][0]
    num_tracks = max(track for track, _ in per_track) + 1
    sides = sorted({side for _, side in per_track})
    num_sides = 2 if sides[-1] == 1 else 1

    layout = SectorLayout(
        encoding=encoding,
        sector_size=sector_size,
        sectors_per_track=sectors_per_track,
        first_record=first_record,
        num_tracks=num_tracks,
        num_sides=num_sides,
        double_stepped=double_stepped,
    )

    slots: dict[tuple[int, int, int], DecodedSector] = {}
    for track, side, s in standard:
        if track % step or s.id.cylinder != track // step:
            continue
        key = (track // step, side, s.id.record)
        slots.setdefault(key, s)

    out = bytearray()
    missing = []
    blank = bytes([fill]) * sector_size
    for track in range(num_tracks):
        for side in range(num_sides):
            for record in range(first_record, first_record + sectors_per_track):
                sector = slots.get((track, side, record))
                if sector is None:
                    missing.append((track, side, record))
                    out += blank
                else:
                    out += sector.data
    return FlatImage(bytes(out), layout, tuple(missing), _suffix(layout))


def _double_stepped(standard: list[tuple[int, int, DecodedSector]]) -> bool:
    """Whether ID cylinders run at half the physical track number."""
    single = sum(1 for track, _, s in standard if s.id.cylinder == track)
    double = sum(1 for track, _, s in standard if s.id.cylinder * 2 == track and track)
    return double > single


def _suffix(layout: SectorLayout) -> str | None:
    if layout.sector_size == 256 and layout.sectors_per_track in (10, 16, 18):
        if layout.encoding is Encoding.MFM and layout.sectors_per_track == 16:
            if layout.num_sides == 2:
                return ".adl"
            return ".adm" if layout.num_tracks > 40 else ".ads"
        return ".dsd" if layout.num_sides == 2 else ".ssd"
    if layout.encoding is Encoding.MFM and layout.sector_size == 1024:
        return ".adf"
    return None

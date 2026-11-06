"""Decode FM and MFM tracks into sectors.

Every track is searched for both FM and MFM address marks at every bit
offset, whatever the HFE header claims. That finds mixed-density tracks,
and marks that no byte or word grid would line up with. Each ID address
mark found becomes a :class:`DecodedSector`, including ones with bad CRCs,
duplicate or out-of-range IDs, odd sizes, or no data field. Nothing is
discarded at this level; deciding which sectors make up the logical disc
is the job of :mod:`oaknut.hfe.flatten`.

An FM half-cell spans two samples at the usual 250 kbit/s HFE rate. The
samples are combined into half-cells at each possible phase and every
phase is decoded, so a transition that slips by one sample part-way round
a track still decodes. Sectors found at more than one phase are merged,
keeping the best read.

Sectors that span the index are decoded by reading on round the track.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from oaknut.hfe.container import HFEHeader, HFEImage, TrackSamples
from oaknut.hfe.ibm import (
    BYTE_HALF_CELLS,
    DATA_MARK,
    DELETED_DATA_MARK,
    FM_DATA_MARK,
    FM_DELETED_DATA_MARK,
    FM_ID_MARK,
    ID_MARK,
    MFM_SYNC,
    MFM_SYNC_CRC,
    crc16,
    decode_byte,
    decode_bytes,
)

__all__ = [
    "Encoding",
    "DataMark",
    "SectorID",
    "DecodedSector",
    "DecodedTrack",
    "DecodedDisc",
    "decode_track",
    "decode_image",
]

#: How far past an ID field to look for its data mark, in bytes. Standard
#: gaps put it 17 (FM) or 34 (MFM) bytes on.
_FM_DATA_MARK_WINDOW = 43
_MFM_DATA_MARK_WINDOW = 60

_MFM_SYNC3 = MFM_SYNC * 3
_BYTE = BYTE_HALF_CELLS


class Encoding(Enum):
    """Recording density."""

    FM = "FM"
    MFM = "MFM"


class DataMark(Enum):
    """The address mark that introduces a data field."""

    NORMAL = "normal"
    DELETED = "deleted"


@dataclass(frozen=True, order=True)
class SectorID:
    """The C/H/R/N fields of an ID address mark."""

    cylinder: int
    head: int
    record: int
    size_code: int

    def size(self, encoding: Encoding) -> int:
        """Data-field length in bytes.

        The 8271 (FM) honours three bits of the size code, up to 16 KiB;
        the WD1770 (and so any MFM disc) honours two, up to 1 KiB.
        """
        bits = 7 if encoding is Encoding.FM else 3
        return 128 << (self.size_code & bits)


@dataclass(frozen=True)
class DecodedSector:
    """One ID address mark and the data field that follows it, if any."""

    encoding: Encoding
    #: Sample offset of the address mark from the start of the track.
    position: int
    id: SectorID
    id_crc_ok: bool
    #: ``None`` when no data mark follows the ID.
    data_mark: DataMark | None = None
    data: bytes | None = None
    data_crc_ok: bool | None = None

    @property
    def readable(self) -> bool:
        """Whether a controller would read this sector without error."""
        return self.id_crc_ok and self.data_crc_ok is True


@dataclass(frozen=True)
class DecodedTrack:
    """The sectors decoded from one side of one physical track."""

    track: int
    side: int
    #: In order of position round the track.
    sectors: tuple[DecodedSector, ...]
    sample_count: int = 0
    weak_samples: int = 0


@dataclass(frozen=True)
class DecodedDisc:
    """Every track of an HFE image, decoded."""

    header: HFEHeader
    #: Ordered by track, then side.
    tracks: tuple[DecodedTrack, ...]

    def track(self, track: int, side: int) -> DecodedTrack:
        """The decoded *track* on *side*.

        Raises:
            KeyError: The image has no such track.
        """
        for decoded in self.tracks:
            if decoded.track == track and decoded.side == side:
                return decoded
        raise KeyError((track, side))

    @property
    def num_sides(self) -> int:
        return self.header.num_sides


def decode_image(image: HFEImage) -> DecodedDisc:
    """Decode every track of *image*."""
    header = image.header
    tracks = []
    for track in range(header.num_tracks):
        for side in range(header.num_sides):
            samples = image.track(track, side)
            tracks.append(
                DecodedTrack(
                    track=track,
                    side=side,
                    sectors=decode_track(samples, bitrate_kbps=header.bitrate_kbps),
                    sample_count=len(samples.samples),
                    weak_samples=samples.weak_samples,
                )
            )
    return DecodedDisc(header, tuple(tracks))


def decode_track(
    samples: TrackSamples | str, *, bitrate_kbps: int = 250
) -> tuple[DecodedSector, ...]:
    """Every sector on one track's *samples*, in order round the track."""
    if isinstance(samples, TrackSamples):
        samples = samples.samples
    if not samples or "1" not in samples:
        return ()
    found: list[DecodedSector] = []
    for encoding, nominal_kbps, scan in (
        (Encoding.FM, 125, _scan_fm),
        (Encoding.MFM, 250, _scan_mfm),
    ):
        per_cell, remainder = divmod(bitrate_kbps, nominal_kbps)
        if remainder or per_cell == 0:
            continue
        for phase in range(per_cell):
            cells = _half_cells(samples, per_cell, phase)
            for position, sector in scan(cells):
                found.append(_at(sector, (phase + position * per_cell) % len(samples)))
    return _merge(found, len(samples))


def _half_cells(samples: str, per_cell: int, phase: int) -> str:
    """Half-cells from *samples*, a transition anywhere in a cell setting it."""
    if per_cell == 1:
        return samples
    lanes = [samples[phase + offset :: per_cell] for offset in range(per_cell)]
    length = min(len(lane) for lane in lanes)
    combined = 0
    for lane in lanes:
        combined |= int(lane[:length], 2) if length else 0
    return format(combined, f"0{length}b") if length else ""


def _at(sector: DecodedSector, position: int) -> DecodedSector:
    return DecodedSector(
        sector.encoding,
        position,
        sector.id,
        sector.id_crc_ok,
        sector.data_mark,
        sector.data,
        sector.data_crc_ok,
    )


def _quality(sector: DecodedSector) -> tuple[bool, bool, bool]:
    return (sector.readable, sector.id_crc_ok, sector.data_mark is not None)


def _merge(found: Iterable[DecodedSector], track_length: int) -> tuple[DecodedSector, ...]:
    """One sector per address mark: merge reads of the same mark at different phases."""
    merged: list[DecodedSector] = []
    for sector in sorted(found, key=lambda s: s.position):
        if merged:
            previous = merged[-1]
            if (
                sector.encoding is previous.encoding
                and sector.position - previous.position < 4 * _BYTE
            ):
                if _quality(sector) > _quality(previous):
                    merged[-1] = sector
                continue
        merged.append(sector)
    # The same mark can surface either side of the track's start.
    if len(merged) > 1:
        first, last = merged[0], merged[-1]
        if (
            first.encoding is last.encoding
            and first.position + track_length - last.position < 4 * _BYTE
        ):
            best = first if _quality(first) >= _quality(last) else last
            merged = [best, *merged[1:-1]] if best is first else merged[1:]
    return tuple(merged)


def _scan_fm(cells: str):
    length = len(cells)
    ring = cells + cells
    position = ring.find(FM_ID_MARK)
    while 0 <= position < length:
        id_bytes = decode_bytes(ring, position + _BYTE, 6)
        identifier = SectorID(*id_bytes[:4])
        id_crc_ok = crc16(bytes([ID_MARK]) + id_bytes[:4]) == int.from_bytes(id_bytes[4:], "big")
        sector = DecodedSector(Encoding.FM, position, identifier, id_crc_ok)

        start = position + 7 * _BYTE
        end = start + _FM_DATA_MARK_WINDOW * _BYTE
        candidates = [
            (found, mark)
            for pattern, mark in (
                (FM_DATA_MARK, DATA_MARK),
                (FM_DELETED_DATA_MARK, DELETED_DATA_MARK),
            )
            if (found := ring.find(pattern, start, end)) >= 0
        ]
        if candidates:
            data_position, mark = min(candidates)
            size = identifier.size(Encoding.FM)
            field = decode_bytes(ring, data_position + _BYTE, size + 2)
            sector = _with_data(
                sector, mark, field[:size], crc16(bytes([mark]) + field[:size]), field[size:]
            )
        yield position, sector
        position = ring.find(FM_ID_MARK, position + _BYTE)


def _scan_mfm(cells: str):
    length = len(cells)
    ring = cells + cells
    position = ring.find(_MFM_SYNC3)
    while 0 <= position < length:
        mark = decode_byte(ring[position + 3 * _BYTE : position + 4 * _BYTE])
        if mark == ID_MARK:
            id_bytes = decode_bytes(ring, position + 4 * _BYTE, 6)
            identifier = SectorID(*id_bytes[:4])
            id_crc = crc16(bytes([ID_MARK]) + id_bytes[:4], MFM_SYNC_CRC)
            sector = DecodedSector(
                Encoding.MFM,
                position,
                identifier,
                id_crc == int.from_bytes(id_bytes[4:], "big"),
            )
            search = position + 10 * _BYTE
            end = search + _MFM_DATA_MARK_WINDOW * _BYTE
            while (data_position := ring.find(_MFM_SYNC3, search, end)) >= 0:
                data_mark = decode_byte(ring[data_position + 3 * _BYTE : data_position + 4 * _BYTE])
                if data_mark in (DATA_MARK, DELETED_DATA_MARK):
                    size = identifier.size(Encoding.MFM)
                    field = decode_bytes(ring, data_position + 4 * _BYTE, size + 2)
                    crc = crc16(bytes([data_mark]) + field[:size], MFM_SYNC_CRC)
                    sector = _with_data(sector, data_mark, field[:size], crc, field[size:])
                    break
                if data_mark == ID_MARK:
                    break  # the next sector's ID: this one has no data field
                search = data_position + _BYTE
            yield position, sector
        position = ring.find(_MFM_SYNC3, position + _BYTE)


def _with_data(
    sector: DecodedSector, mark: int, data: bytes, computed_crc: int, stored_crc: bytes
) -> DecodedSector:
    return DecodedSector(
        sector.encoding,
        sector.position,
        sector.id,
        sector.id_crc_ok,
        DataMark.DELETED if mark == DELETED_DATA_MARK else DataMark.NORMAL,
        data,
        computed_crc == int.from_bytes(stored_crc, "big"),
    )

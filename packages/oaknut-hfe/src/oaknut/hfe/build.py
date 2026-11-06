"""Build FM and MFM tracks from sector descriptions.

The inverse of :mod:`oaknut.hfe.decode`: lay sectors out as an Acorn
controller would format them, then convert the half-cells to HFE samples
for :func:`oaknut.hfe.container.write_hfe`. Each :class:`FormattedSector`
can carry the defects copy protection uses — any ID, a bad ID or data
CRC, a deleted-data mark, a missing data field — so decoder behaviour can
be tested without real captures of every trick.

Ported from Beebium's ``TrackBuilder``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from oaknut.hfe.decode import Encoding, SectorID
from oaknut.hfe.ibm import (
    DATA_MARK,
    DELETED_DATA_MARK,
    FM_DATA_MARK,
    FM_DELETED_DATA_MARK,
    FM_ID_MARK,
    ID_MARK,
    MFM_SYNC,
    MFM_SYNC_CRC,
    crc16,
    fm_encode,
    mfm_encode,
)

__all__ = [
    "FormattedSector",
    "build_track",
    "track_samples",
    "samples_per_half_cell",
    "TRACK_SAMPLES_300RPM_250KBPS",
]

#: Samples in one revolution at 300 rpm on a 250 kbit/s HFE clock.
TRACK_SAMPLES_300RPM_250KBPS = 100_000


@dataclass(frozen=True)
class FormattedSector:
    """One sector as formatted onto a track."""

    id: SectorID
    #: The data field; padded with zeros, or truncated, to the ID's size.
    data: bytes = b""
    deleted: bool = False
    #: Write no data field at all after the ID.
    omit_data: bool = False
    #: Corrupt the stored ID CRC.
    bad_id_crc: bool = False
    #: Corrupt the stored data CRC.
    bad_data_crc: bool = False


@dataclass(frozen=True)
class _Layout:
    gap1: int
    sync: int
    gap2: int
    gap3: int
    gap_byte: int


_FM_LAYOUT = _Layout(gap1=16, sync=6, gap2=11, gap3=21, gap_byte=0xFF)
_MFM_LAYOUT = _Layout(gap1=50, sync=12, gap2=22, gap3=24, gap_byte=0x4E)


def build_track(
    sectors: Iterable[FormattedSector],
    encoding: Encoding,
    *,
    half_cells: int | None = None,
) -> str:
    """The half-cells of a track holding *sectors* in the order given.

    The track is padded with gap bytes to *half_cells* when given (one
    revolution at 300 rpm is 50,000 FM or 100,000 MFM half-cells).

    Raises:
        ValueError: The sectors do not fit in *half_cells*.
    """
    if encoding is Encoding.FM:
        cells = _fm_track(sectors)
        filler = fm_encode(bytes([_FM_LAYOUT.gap_byte]))
    else:
        cells = _mfm_track(sectors)
        filler = mfm_encode(bytes([_MFM_LAYOUT.gap_byte]))
    if half_cells is not None:
        if len(cells) > half_cells:
            raise ValueError(f"track needs {len(cells)} half-cells; only {half_cells} fit")
        cells += (filler * (half_cells // len(filler) + 1))[: half_cells - len(cells)]
    return cells


def _field(sector: FormattedSector, encoding: Encoding) -> tuple[bytes, bytes]:
    identifier = sector.id
    id_bytes = bytes(
        [identifier.cylinder, identifier.head, identifier.record, identifier.size_code]
    )
    data = sector.data[: identifier.size(encoding)].ljust(identifier.size(encoding), b"\x00")
    return id_bytes, data


def _crc_bytes(crc: int, corrupt: bool) -> bytes:
    return (crc ^ (0x5A5A if corrupt else 0)).to_bytes(2, "big")


def _fm_track(sectors: Iterable[FormattedSector]) -> str:
    layout = _FM_LAYOUT
    gap = bytes([layout.gap_byte])
    parts = [fm_encode(gap * layout.gap1)]
    for sector in sectors:
        id_bytes, data = _field(sector, Encoding.FM)
        parts.append(fm_encode(b"\x00" * layout.sync))
        parts.append(FM_ID_MARK)
        id_crc = crc16(bytes([ID_MARK]) + id_bytes)
        parts.append(fm_encode(id_bytes + _crc_bytes(id_crc, sector.bad_id_crc)))
        parts.append(fm_encode(gap * layout.gap2))
        if not sector.omit_data:
            mark = DELETED_DATA_MARK if sector.deleted else DATA_MARK
            parts.append(fm_encode(b"\x00" * layout.sync))
            parts.append(FM_DELETED_DATA_MARK if sector.deleted else FM_DATA_MARK)
            data_crc = crc16(bytes([mark]) + data)
            parts.append(fm_encode(data + _crc_bytes(data_crc, sector.bad_data_crc)))
        parts.append(fm_encode(gap * layout.gap3))
    return "".join(parts)


class _MFMWriter:
    def __init__(self):
        self._parts: list[str] = []
        self._last_bit = 0

    def bytes(self, data: bytes) -> None:
        if data:
            self._parts.append(mfm_encode(data, self._last_bit))
            self._last_bit = data[-1] & 1

    def sync(self) -> None:
        self._parts.append(MFM_SYNC * 3)
        self._last_bit = 1  # 0xA1 ends in a 1

    def cells(self) -> str:
        return "".join(self._parts)


def _mfm_track(sectors: Iterable[FormattedSector]) -> str:
    layout = _MFM_LAYOUT
    gap = bytes([layout.gap_byte])
    writer = _MFMWriter()
    writer.bytes(gap * layout.gap1)
    for sector in sectors:
        id_bytes, data = _field(sector, Encoding.MFM)
        writer.bytes(b"\x00" * layout.sync)
        writer.sync()
        id_crc = crc16(bytes([ID_MARK]) + id_bytes, MFM_SYNC_CRC)
        writer.bytes(bytes([ID_MARK]) + id_bytes + _crc_bytes(id_crc, sector.bad_id_crc))
        writer.bytes(gap * layout.gap2)
        if not sector.omit_data:
            mark = DELETED_DATA_MARK if sector.deleted else DATA_MARK
            writer.bytes(b"\x00" * layout.sync)
            writer.sync()
            data_crc = crc16(bytes([mark]) + data, MFM_SYNC_CRC)
            writer.bytes(bytes([mark]) + data + _crc_bytes(data_crc, sector.bad_data_crc))
        writer.bytes(gap * layout.gap3)
    return writer.cells()


def samples_per_half_cell(encoding: Encoding, bitrate_kbps: int = 250) -> int:
    """HFE samples per half-cell: an FM half-cell is 4 µs, an MFM one 2 µs.

    Raises:
        ValueError: The bit rate does not give a whole number of samples.
    """
    nominal = 125 if encoding is Encoding.FM else 250
    count, remainder = divmod(bitrate_kbps, nominal)
    if remainder or count == 0:
        raise ValueError(f"{encoding.value} cannot be sampled at {bitrate_kbps} kbit/s")
    return count


def track_samples(half_cells: str, encoding: Encoding, bitrate_kbps: int = 250) -> str:
    """HFE samples for *half_cells*, each transition at the end of its cell."""
    count = samples_per_half_cell(encoding, bitrate_kbps)
    if count == 1:
        return half_cells
    pad = "0" * (count - 1)
    return "".join(pad + cell for cell in half_cells)

"""The HFE file container.

An HFE file starts with a 512-byte header, followed at
``track_list_offset * 512`` by a track lookup table of four bytes per
track: the track's offset in 512-byte blocks and its length in bytes,
both little-endian. A track's length covers both sides, which are
interleaved in 256-byte halves of each 512-byte block: the first half
belongs to side 0, the second to side 1.

Every byte holds eight flux *samples*, least significant bit first, on a
clock of twice the header's bit rate: at 250 kbit/s a sample is 2 µs. A
``1`` sample is a flux transition. (So one FM half-cell spans two samples
and one MFM half-cell spans one; see :mod:`oaknut.hfe.ibm`.)

Version 3 (``HXCHFEV3``) adds in-stream opcodes, recognised by a high
nibble of ``0xF`` after bit reversal, which cannot occur in valid FM or
MFM data:

========== ==== ===================================================
NOP        F0   no samples
SETINDEX   F1   the index pulse occurs here
SETBITRATE F2   the next byte *n* sets the rate to 36 MHz / (2 *n*)
SKIPBITS   F3   the next byte *n*: skip the first *n* samples of the
                byte after it
RAND       F4   eight weak samples, which read differently each time
========== ==== ===================================================

Version 1 (``HXCPICFE``) has no opcodes. Weak samples read here as zeros
(no transition), and are counted in :attr:`TrackSamples.weak_samples`.

Ported from Beebium's ``HfeFormatHandler``.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from oaknut.hfe.exceptions import HFEFormatError

__all__ = [
    "HFEFormatError",
    "HFEHeader",
    "HFEImage",
    "TrackEncoding",
    "TrackSamples",
    "HFE_V1_SIGNATURE",
    "HFE_V3_SIGNATURE",
    "write_hfe",
]

HFE_V1_SIGNATURE = b"HXCPICFE"
HFE_V3_SIGNATURE = b"HXCHFEV3"

_BLOCK_SIZE = 512
_HALF_BLOCK = 256
_HEADER = struct.Struct("<8sBBBBHHBBHBB")
_LUT_ENTRY = struct.Struct("<HH")

_NOP = 0xF0
_SETINDEX = 0xF1
_SETBITRATE = 0xF2
_SKIPBITS = 0xF3
_RAND = 0xF4

#: The HxC sample-clock base frequency that SETBITRATE divides.
_BITRATE_CLOCK_HZ = 36_000_000

_REVERSED = bytes(int(f"{byte:08b}"[::-1], 2) for byte in range(256))
_SAMPLES = tuple(f"{byte:08b}" for byte in range(256))


class TrackEncoding(IntEnum):
    """The track-encoding hint in the HFE header.

    Capture tools set it from what they expected, not what they found, so
    the decoder searches every track for both FM and MFM regardless.
    """

    ISOIBM_MFM = 0
    AMIGA_MFM = 1
    ISOIBM_FM = 2
    EMU_FM = 3
    UNKNOWN = 0xFF


@dataclass(frozen=True)
class HFEHeader:
    """The fields of an HFE file header."""

    version: int
    num_tracks: int
    num_sides: int
    #: A :class:`TrackEncoding`, or the raw byte when it is not one.
    track_encoding: TrackEncoding | int
    bitrate_kbps: int
    rpm: int
    interface_mode: int
    track_list_offset: int
    write_allowed: bool
    #: False when the image is meant for a double-stepping drive.
    single_step: bool


@dataclass(frozen=True)
class TrackSamples:
    """The flux samples of one side of one track, in time order."""

    #: ``"0"``/``"1"`` samples; ``"1"`` is a flux transition.
    samples: str
    #: How many of :attr:`samples` came from weak (RAND) bytes.
    weak_samples: int = 0
    #: Sample positions of SETINDEX opcodes.
    index_positions: tuple[int, ...] = ()
    #: Bit rates set by SETBITRATE opcodes, in kbit/s, in order.
    bitrates_kbps: tuple[int, ...] = ()


class HFEImage:
    """A parsed HFE file, decoding each track's samples on demand."""

    def __init__(self, data: bytes, header: HFEHeader):
        self._data = data
        self._header = header

    @classmethod
    def from_filepath(cls, filepath: Path) -> HFEImage:
        """Read and parse the HFE file at *filepath*."""
        return cls.from_bytes(Path(filepath).read_bytes())

    @classmethod
    def from_bytes(cls, data: bytes) -> HFEImage:
        """Parse an HFE file held in *data*.

        Raises:
            HFEFormatError: The header is not a valid HFE v1 or v3 header.
        """
        data = bytes(data)
        if len(data) < _BLOCK_SIZE:
            raise HFEFormatError(f"too short to be an HFE file ({len(data)} bytes)")
        (
            signature,
            revision,
            num_tracks,
            num_sides,
            track_encoding,
            bitrate_kbps,
            rpm,
            interface_mode,
            _unused,
            track_list_offset,
            write_allowed,
            single_step,
        ) = _HEADER.unpack_from(data)
        if signature == HFE_V1_SIGNATURE:
            version = 1
        elif signature == HFE_V3_SIGNATURE:
            version = 3
        else:
            raise HFEFormatError(f"not an HFE file: signature {signature!r}")
        if revision != 0:
            raise HFEFormatError(f"unsupported HFE format revision {revision}")
        if num_sides not in (1, 2):
            raise HFEFormatError(f"invalid HFE side count {num_sides}")
        if num_tracks == 0:
            raise HFEFormatError("HFE header declares no tracks")
        lut_end = track_list_offset * _BLOCK_SIZE + num_tracks * _LUT_ENTRY.size
        if track_list_offset == 0 or lut_end > len(data):
            raise HFEFormatError(
                f"HFE track list at block {track_list_offset} lies beyond the end of the file"
            )
        try:
            track_encoding = TrackEncoding(track_encoding)
        except ValueError:
            pass
        header = HFEHeader(
            version=version,
            num_tracks=num_tracks,
            num_sides=num_sides,
            track_encoding=track_encoding,
            bitrate_kbps=bitrate_kbps,
            rpm=rpm,
            interface_mode=interface_mode,
            track_list_offset=track_list_offset,
            write_allowed=write_allowed != 0,
            single_step=single_step != 0,
        )
        return cls(data, header)

    @property
    def header(self) -> HFEHeader:
        return self._header

    def track(self, track: int, side: int) -> TrackSamples:
        """The samples of physical *track* on *side*.

        Raises:
            IndexError: *track* or *side* is outside the image.
            HFEFormatError: The track's data runs past the end of the file.
        """
        header = self._header
        if not 0 <= track < header.num_tracks:
            raise IndexError(f"track {track} outside 0-{header.num_tracks - 1}")
        if not 0 <= side < header.num_sides:
            raise IndexError(f"side {side} outside 0-{header.num_sides - 1}")
        block, length = _LUT_ENTRY.unpack_from(
            self._data, header.track_list_offset * _BLOCK_SIZE + track * _LUT_ENTRY.size
        )
        start = block * _BLOCK_SIZE
        side_length = length // 2
        raw = bytearray()
        for offset in range(0, side_length, _HALF_BLOCK):
            chunk = min(_HALF_BLOCK, side_length - offset)
            position = start + 2 * offset + side * _HALF_BLOCK
            if position + chunk > len(self._data):
                raise HFEFormatError(
                    f"track {track} side {side} data runs beyond the end of the file"
                )
            raw += self._data[position : position + chunk]
        return _decode_stream(raw.translate(_REVERSED), opcodes=header.version == 3)


def _decode_stream(stream: bytes, *, opcodes: bool) -> TrackSamples:
    """Samples from bit-reversed (time-ordered) track bytes."""
    if not opcodes:
        return TrackSamples("".join(_SAMPLES[byte] for byte in stream))
    parts: list[str] = []
    length = 0
    weak = 0
    index_positions: list[int] = []
    bitrates: list[int] = []
    i = 0
    end = len(stream)
    while i < end:
        byte = stream[i]
        if byte & 0xF0 != 0xF0:
            parts.append(_SAMPLES[byte])
            length += 8
            i += 1
        elif byte == _RAND:
            parts.append("00000000")
            length += 8
            weak += 8
            i += 1
        elif byte == _SETINDEX:
            index_positions.append(length)
            i += 1
        elif byte == _SETBITRATE:
            if i + 1 < end and stream[i + 1]:
                bitrates.append(round(_BITRATE_CLOCK_HZ / (2 * stream[i + 1]) / 1000))
            i += 2
        elif byte == _SKIPBITS:
            if i + 2 < end:
                kept = _SAMPLES[stream[i + 2]][min(stream[i + 1], 8) :]
                parts.append(kept)
                length += len(kept)
            i += 3
        else:  # NOP, and opcodes this reader does not know
            i += 1
    return TrackSamples("".join(parts), weak, tuple(index_positions), tuple(bitrates))


def write_hfe(
    tracks: Sequence[Sequence[str]],
    *,
    version: int = 3,
    track_encoding: TrackEncoding | int = TrackEncoding.ISOIBM_FM,
    bitrate_kbps: int = 250,
    rpm: int = 300,
    interface_mode: int = 7,
) -> bytes:
    """An HFE file holding *tracks*.

    *tracks* is indexed ``[track][side]``; each entry is a sample string of
    ``"0"``, ``"1"`` and, in v3, ``"?"`` for weak samples, which must fill
    whole, byte-aligned groups of eight. Sides are padded with zero samples
    to whole bytes and to a common length.

    Raises:
        ValueError: The sides disagree in number, weak samples are given for
            v1 or misaligned, or (v3) a byte of samples would read back as
            an opcode.
    """
    if version not in (1, 3):
        raise ValueError(f"HFE version must be 1 or 3, not {version}")
    num_sides = len(tracks[0]) if tracks else 1
    if not tracks or any(len(sides) != num_sides for sides in tracks) or num_sides not in (1, 2):
        raise ValueError("every track needs the same number of sides, one or two")

    encoded_tracks = []
    for sides in tracks:
        encoded = [_encode_stream(samples, version) for samples in sides]
        side_length = max(len(side) for side in encoded)
        encoded_tracks.append([side.ljust(side_length, b"\x00") for side in encoded])

    lut_blocks = 1
    first_track_block = 1 + lut_blocks
    lut = bytearray(b"\xff" * _BLOCK_SIZE)
    body = bytearray()
    for index, sides in enumerate(encoded_tracks):
        side_length = len(sides[0])
        block = first_track_block + len(body) // _BLOCK_SIZE
        _LUT_ENTRY.pack_into(lut, index * _LUT_ENTRY.size, block, 2 * side_length)
        for offset in range(0, side_length, _HALF_BLOCK):
            for side in range(2):
                half = sides[side][offset : offset + _HALF_BLOCK] if side < num_sides else b""
                body += half.ljust(_HALF_BLOCK, b"\x00")

    header = bytearray(b"\xff" * _BLOCK_SIZE)
    _HEADER.pack_into(
        header,
        0,
        HFE_V3_SIGNATURE if version == 3 else HFE_V1_SIGNATURE,
        0,
        len(tracks),
        num_sides,
        int(track_encoding),
        bitrate_kbps,
        rpm,
        interface_mode,
        0xFF,
        1,
        0xFF,
        0xFF,
    )
    return bytes(header + lut + body)


def _encode_stream(samples: str, version: int) -> bytes:
    """File bytes (bit-reversed) for one side's *samples*."""
    out = bytearray()
    for offset in range(0, len(samples), 8):
        group = samples[offset : offset + 8].ljust(8, "0")
        if "?" in group:
            if version != 3:
                raise ValueError("weak samples need HFE v3")
            if group != "????????":
                raise ValueError(f"weak samples at {offset} do not fill a whole byte")
            byte = _RAND
        else:
            byte = int(group, 2)
            if version == 3 and byte & 0xF0 == 0xF0:
                raise ValueError(f"samples at {offset} ({group}) would read back as an opcode")
        out.append(_REVERSED[byte])
    return bytes(out)

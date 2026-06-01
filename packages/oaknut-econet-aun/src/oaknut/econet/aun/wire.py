"""The AUN wire codec: the 8-byte header plus payload."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from oaknut.econet.core import EconetError

# type, port, control, pad, handle (handle is a little-endian uint32).
_HEADER = struct.Struct("<BBBBI")
_HEADER_SIZE = _HEADER.size  # 8
_BYTE_RANGE = range(0x00, 0x100)
_U32_RANGE = range(0x00, 0x1_0000_0000)


class AunType(IntEnum):
    """The AUN packet type — the first header byte."""

    BROADCAST = 1
    UNICAST = 2
    ACK = 3
    NACK = 4
    IMMEDIATE = 5
    IMMEDIATE_REPLY = 6


@dataclass(frozen=True, slots=True)
class AunPacket:
    """An AUN datagram: an 8-byte header and a payload.

    The header is type, port, control, a pad byte, and a little-endian uint32
    handle used to correlate a reply with its request. Station addressing is
    *not* in the header — it is resolved from the UDP peer by the transport.
    """

    type: AunType
    port: int
    control: int
    handle: int = 0
    payload: bytes = b""

    def __post_init__(self) -> None:
        if self.port not in _BYTE_RANGE:
            raise ValueError(f"port must be 0..255, got {self.port!r}")
        if self.control not in _BYTE_RANGE:
            raise ValueError(f"control must be 0..255, got {self.control!r}")
        if self.handle not in _U32_RANGE:
            raise ValueError(f"handle must be 0..2**32-1, got {self.handle!r}")

    def encode(self) -> bytes:
        """Serialise to the on-wire byte string."""
        header = _HEADER.pack(int(self.type), self.port, self.control, 0, self.handle)
        return header + self.payload

    @classmethod
    def decode(cls, data: bytes) -> AunPacket:
        """Parse an AUN datagram, raising :class:`EconetError` on malformed input."""
        if len(data) < _HEADER_SIZE:
            raise EconetError(
                f"AUN datagram too short: {len(data)} bytes, need at least {_HEADER_SIZE}"
            )
        type_byte, port, control, _pad, handle = _HEADER.unpack_from(data)
        try:
            aun_type = AunType(type_byte)
        except ValueError as exc:
            raise EconetError(f"unknown AUN type byte {type_byte:#04x}") from exc
        return cls(
            type=aun_type,
            port=port,
            control=control,
            handle=handle,
            payload=data[_HEADER_SIZE:],
        )

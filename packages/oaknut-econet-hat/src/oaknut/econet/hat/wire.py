"""The econet-gpio kernel packet codec: struct __econet_packet_aun.

The kernel exchanges packets with user space in this 12-byte-header format
(see PiEconetBridge's ``econet-gpio-consumer.h``):

    0 dststn  1 dstnet  2 srcstn  3 srcnet  4 aun_ttype  5 port
    6 ctrl    7 padding  8..11 seq (little-endian uint32)  12.. data

The control byte keeps its Econet high bit set here (the kernel only strips it
when a packet is written out to a UDP AUN socket), so — unlike AUN-over-UDP —
no control translation happens at this layer.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from oaknut.econet.core import Address, EconetError

# dststn, dstnet, srcstn, srcnet, aun_ttype, port, ctrl, padding, seq(LE u32)
_HEADER = struct.Struct("<8BI")
_HEADER_SIZE = _HEADER.size  # 12
_BYTE_RANGE = range(0x00, 0x100)
_U32_RANGE = range(0x00, 0x1_0000_0000)


class KernelPacketType(IntEnum):
    """The ``aun_ttype`` field of struct __econet_packet_aun."""

    BROADCAST = 1
    DATA = 2
    ACK = 3
    NAK = 4
    IMMEDIATE = 5
    IMMEDIATE_REPLY = 6
    INK = 7  # "Immediate NAK" — econet-hpbridge only


class TxStatus(IntEnum):
    """The ECONET_TX_* status read back from the TXERR ioctl after a write."""

    SUCCESS = 0x00
    BUSY = 0x10
    JAMMED = 0x40
    HANDSHAKE_FAIL = 0x41
    NOT_LISTENING = 0x42
    NO_CLOCK = 0x43
    UNDERRUN = 0x50
    TDRA_FULL = 0x51
    NO_IRQ = 0x52
    NO_COPY = 0x53
    NOT_START = 0x54
    COLLISION = 0x55
    INVALID = 0xFC
    DATA_PROGRESS = 0xFD
    IN_PROGRESS = 0xFE
    START_WAIT = 0xFF


@dataclass(frozen=True, slots=True)
class KernelPacket:
    """One packet as exchanged with the econet-gpio character device."""

    ttype: KernelPacketType
    dst: Address
    src: Address
    control: int
    port: int
    seq: int = 0
    payload: bytes = b""

    def __post_init__(self) -> None:
        if self.control not in _BYTE_RANGE:
            raise ValueError(f"control must be 0..255, got {self.control!r}")
        if self.port not in _BYTE_RANGE:
            raise ValueError(f"port must be 0..255, got {self.port!r}")
        if self.seq not in _U32_RANGE:
            raise ValueError(f"seq must be 0..2**32-1, got {self.seq!r}")

    def encode(self) -> bytes:
        header = _HEADER.pack(
            self.dst.station,
            self.dst.network,
            self.src.station,
            self.src.network,
            int(self.ttype),
            self.port,
            self.control,
            0,
            self.seq,
        )
        return header + self.payload

    @classmethod
    def decode(cls, data: bytes) -> KernelPacket:
        if len(data) < _HEADER_SIZE:
            raise EconetError(
                f"kernel packet too short: {len(data)} bytes, need at least {_HEADER_SIZE}"
            )
        dststn, dstnet, srcstn, srcnet, ttype, port, control, _pad, seq = _HEADER.unpack_from(data)
        try:
            packet_type = KernelPacketType(ttype)
        except ValueError as exc:
            raise EconetError(f"unknown kernel packet type {ttype:#04x}") from exc
        return cls(
            ttype=packet_type,
            dst=Address(dstnet, dststn),
            src=Address(srcnet, srcstn),
            control=control,
            port=port,
            seq=seq,
            payload=data[_HEADER_SIZE:],
        )

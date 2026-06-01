"""The Econet logical packet — the currency every transport speaks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from oaknut.econet.core.addressing import Address

_BYTE_RANGE = range(0x00, 0x100)


class PacketKind(Enum):
    """The kind of an Econet packet at the logical (post-handshake) level.

    ``ACK``/``NACK`` are deliberately absent: inbound packets are already
    acknowledged below the transport boundary, so acknowledgement is a
    transmit *outcome*, not a packet a caller receives.
    """

    BROADCAST = auto()
    UNICAST = auto()
    IMMEDIATE = auto()
    IMMEDIATE_REPLY = auto()


@dataclass(frozen=True, slots=True)
class EconetPacket:
    """A logical Econet packet: a completed transaction's worth of data.

    Modelled on the AUN packet. The four-way handshake (scout / scout-ack /
    data / final-ack) is resolved below the transport boundary, so this is the
    unit applications send and receive.

    ``seq`` is the transport-managed sequence/handle used for AUN reply
    correlation; it is normally ``None`` at the application layer.
    """

    kind: PacketKind
    dst: Address
    src: Address
    control: int
    port: int
    payload: bytes = b""
    seq: int | None = None

    def __post_init__(self) -> None:
        if self.control not in _BYTE_RANGE:
            raise ValueError(f"control must be 0..255, got {self.control!r}")
        if self.port not in _BYTE_RANGE:
            raise ValueError(f"port must be 0..255, got {self.port!r}")

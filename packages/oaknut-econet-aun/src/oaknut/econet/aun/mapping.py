"""Mapping between the logical EconetPacket and the AUN wire packet.

The AUN header carries no station addresses — those are resolved from the UDP
peer by the transport — so these functions translate only the framing: the
:class:`PacketKind` <-> :class:`AunType` correspondence and the control byte.
AUN transmits the Econet control byte with its high bit cleared; the receiver
restores it.
"""

from __future__ import annotations

from oaknut.econet.aun.wire import AunPacket, AunType
from oaknut.econet.core import Address, EconetError, EconetPacket, PacketKind

_KIND_TO_TYPE = {
    PacketKind.BROADCAST: AunType.BROADCAST,
    PacketKind.UNICAST: AunType.UNICAST,
    PacketKind.IMMEDIATE: AunType.IMMEDIATE,
    PacketKind.IMMEDIATE_REPLY: AunType.IMMEDIATE_REPLY,
}
_TYPE_TO_KIND = {aun_type: kind for kind, aun_type in _KIND_TO_TYPE.items()}

#: The control-byte bit AUN strips on the wire and the receiver restores.
_CONTROL_HIGH_BIT = 0x80


def aun_type_for_kind(kind: PacketKind) -> AunType:
    """The AUN type carrying a logical packet of *kind*."""
    return _KIND_TO_TYPE[kind]


def kind_for_aun_type(aun_type: AunType) -> PacketKind:
    """The logical kind for a data-bearing AUN type.

    ACK and NACK are wire-level control responses, not packets an application
    receives; asking for their kind raises :class:`EconetError`.
    """
    try:
        return _TYPE_TO_KIND[aun_type]
    except KeyError as exc:
        raise EconetError(
            f"AUN {aun_type.name} is a wire control response, not a logical packet"
        ) from exc


def econet_to_aun(packet: EconetPacket, *, handle: int) -> AunPacket:
    """Build the AUN packet for *packet*, stamping the transport's *handle*."""
    return AunPacket(
        type=aun_type_for_kind(packet.kind),
        port=packet.port,
        control=packet.control & ~_CONTROL_HIGH_BIT,
        handle=handle,
        payload=packet.payload,
    )


def aun_to_econet(aun: AunPacket, *, dst: Address, src: Address) -> EconetPacket:
    """Build the logical packet for *aun*, applying peer-resolved addresses."""
    return EconetPacket(
        kind=kind_for_aun_type(aun.type),
        dst=dst,
        src=src,
        control=aun.control | _CONTROL_HIGH_BIT,
        port=aun.port,
        payload=aun.payload,
        seq=aun.handle,
    )

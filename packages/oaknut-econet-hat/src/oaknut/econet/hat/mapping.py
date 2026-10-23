"""Mapping between EconetPacket and the kernel's KernelPacket, plus helpers.

The kernel struct already carries full addressing and the raw Econet control
byte (high bit intact), so the mapping is a straight field correspondence with
no control translation. Also here: the 8192-byte station-interest bitmap (one
bit per net*32 + stn, matching the ECONET_SET_STATION macro) and the TX-status
classification used by the device layer.
"""

from __future__ import annotations

from oaknut.econet.core import (
    Address,
    EconetError,
    EconetPacket,
    PacketKind,
    TransmitOutcome,
)
from oaknut.econet.hat.wire import KernelPacket, KernelPacketType, TxStatus

#: Size of the station-interest bitmap passed to the SET_STATIONS ioctl.
STATION_MAP_SIZE = 8192

_KIND_TO_TTYPE = {
    PacketKind.BROADCAST: KernelPacketType.BROADCAST,
    PacketKind.UNICAST: KernelPacketType.DATA,
    PacketKind.IMMEDIATE: KernelPacketType.IMMEDIATE,
    PacketKind.IMMEDIATE_REPLY: KernelPacketType.IMMEDIATE_REPLY,
}
_TTYPE_TO_KIND = {ttype: kind for kind, ttype in _KIND_TO_TTYPE.items()}


def ttype_for_kind(kind: PacketKind) -> KernelPacketType:
    return _KIND_TO_TTYPE[kind]


def kind_for_ttype(ttype: KernelPacketType) -> PacketKind:
    """The logical kind for a data-bearing type; ACK/NAK/INK have none."""
    try:
        return _TTYPE_TO_KIND[ttype]
    except KeyError as exc:
        raise EconetError(f"kernel packet type {ttype.name} carries no logical packet") from exc


def econet_to_kernel(packet: EconetPacket, *, seq: int = 0) -> KernelPacket:
    """Build the kernel packet for *packet* (control byte passes through)."""
    return KernelPacket(
        ttype=ttype_for_kind(packet.kind),
        dst=packet.dst,
        src=packet.src,
        control=packet.control,
        port=packet.port,
        seq=seq,
        payload=packet.payload,
    )


def kernel_to_econet(kernel: KernelPacket) -> EconetPacket | None:
    """Map an inbound kernel packet to an EconetPacket, or None for an
    ACK/NAK/INK handshake artifact that is not a deliverable packet."""
    if kernel.ttype in (KernelPacketType.ACK, KernelPacketType.NAK, KernelPacketType.INK):
        return None
    return EconetPacket(
        kind=kind_for_ttype(kernel.ttype),
        dst=kernel.dst,
        src=kernel.src,
        control=kernel.control,
        port=kernel.port,
        payload=kernel.payload,
        seq=kernel.seq,
    )


# -- station-interest bitmap -----------------------------------------


def empty_station_map() -> bytearray:
    """A cleared station-interest bitmap of the size SET_STATIONS expects."""
    return bytearray(STATION_MAP_SIZE)


def _index_and_mask(address: Address) -> tuple[int, int]:
    return address.network * 32 + address.station // 8, 1 << (address.station % 8)


def set_station(bitmap: bytearray, address: Address) -> None:
    """Mark a station as one we want to receive traffic for."""
    index, mask = _index_and_mask(address)
    bitmap[index] |= mask


def is_station_set(bitmap: bytes, address: Address) -> bool:
    index, mask = _index_and_mask(address)
    return bool(bitmap[index] & mask)


# -- TX status -------------------------------------------------------

_STATUS_TO_OUTCOME = {
    TxStatus.SUCCESS: TransmitOutcome.ACKNOWLEDGED,
    TxStatus.NOT_LISTENING: TransmitOutcome.NOT_LISTENING,
    TxStatus.NO_CLOCK: TransmitOutcome.NO_CLOCK,
    TxStatus.JAMMED: TransmitOutcome.LINE_JAMMED,
    TxStatus.HANDSHAKE_FAIL: TransmitOutcome.HANDSHAKE_FAILED,
}
_IN_PROGRESS = frozenset(
    {TxStatus.IN_PROGRESS, TxStatus.DATA_PROGRESS, TxStatus.START_WAIT}
)


def tx_status_to_outcome(status: TxStatus | int) -> TransmitOutcome:
    """Map a final kernel TX status to a transport-neutral TransmitOutcome."""
    try:
        status = TxStatus(status)
    except ValueError:
        return TransmitOutcome.NETWORK_ERROR
    return _STATUS_TO_OUTCOME.get(status, TransmitOutcome.NETWORK_ERROR)


def is_in_progress(status: TxStatus | int) -> bool:
    """True while a transmission is still underway (keep polling TXERR)."""
    try:
        return TxStatus(status) in _IN_PROGRESS
    except ValueError:
        return False

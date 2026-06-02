"""Frame parsing and the mapping between EconetPacket and the Piconet protocol.

Econet frame layout (confirmed against the Piconet driver):
``[dst_stn, dst_net, src_stn, src_net, ...]``. For a scout or a broadcast the
bytes after the four-address header are ``control, port, ...extra/payload``; a
data frame carries its payload immediately after the header. Piconet exchanges
raw Econet control bytes (high bit intact), so — unlike AUN — no control-byte
translation is needed here.
"""

from __future__ import annotations

from oaknut.econet.core import (
    IMMEDIATE_PORT,
    Address,
    EconetError,
    EconetPacket,
    PacketKind,
    TransmitOutcome,
)
from oaknut.econet.piconet.protocol import (
    PiconetEvent,
    RxBroadcastEvent,
    RxImmediateEvent,
    RxTransmitEvent,
    TxResult,
    bcast_command,
    tx_command,
)

_ADDR_LEN = 4
_SCOUT_MIN_LEN = 6  # 4 address bytes + control + port


def _addresses(frame: bytes) -> tuple[Address, Address]:
    if len(frame) < _ADDR_LEN:
        raise EconetError(f"Econet frame too short for an address header: {len(frame)} bytes")
    destination = Address(frame[1], frame[0])
    source = Address(frame[3], frame[2])
    return destination, source


# -- inbound: events -> EconetPacket ---------------------------------


def event_to_econet(event: PiconetEvent) -> EconetPacket | None:
    """Map an inbound RX event to an EconetPacket, or None if not a packet."""
    if isinstance(event, RxBroadcastEvent):
        return _frame_to_packet(event.frame, PacketKind.BROADCAST)
    if isinstance(event, RxTransmitEvent):
        return _scout_and_data_to_packet(event.scout, event.data, force_immediate=False)
    if isinstance(event, RxImmediateEvent):
        return _scout_and_data_to_packet(event.scout, event.data, force_immediate=True)
    # TX_RESULT, STATUS, ERROR, and MONITOR are not deliverable packets here.
    return None


def _frame_to_packet(frame: bytes, kind: PacketKind) -> EconetPacket:
    if len(frame) < _SCOUT_MIN_LEN:
        raise EconetError(f"Econet frame too short: {len(frame)} bytes, need at least 6")
    destination, source = _addresses(frame)
    return EconetPacket(
        kind=kind,
        dst=destination,
        src=source,
        control=frame[4],
        port=frame[5],
        payload=bytes(frame[6:]),
    )


def _scout_and_data_to_packet(scout: bytes, data: bytes, *, force_immediate: bool) -> EconetPacket:
    if len(scout) < _SCOUT_MIN_LEN:
        raise EconetError(f"scout frame too short: {len(scout)} bytes, need at least 6")
    destination, source = _addresses(scout)
    control = scout[4]
    port = scout[5]
    payload = bytes(data[_ADDR_LEN:]) if len(data) >= _ADDR_LEN else b""
    immediate = force_immediate or port == IMMEDIATE_PORT
    return EconetPacket(
        kind=PacketKind.IMMEDIATE if immediate else PacketKind.UNICAST,
        dst=destination,
        src=source,
        control=control,
        port=port,
        payload=payload,
    )


# -- outbound: EconetPacket -> commands ------------------------------


def econet_to_tx_command(packet: EconetPacket) -> str:
    """Format the TX command that sends *packet* (a unicast or immediate)."""
    return tx_command(
        station=packet.dst.station,
        network=packet.dst.network,
        control=packet.control,
        port=packet.port,
        data=packet.payload,
    )


def broadcast_command_for(payload: bytes, *, port: int, control: int) -> str:
    """Format a BCAST command. The firmware prepends the address header; the
    body must carry the control byte and port ahead of the payload."""
    body = bytes([control, port]) + payload
    return bcast_command(body)


_TX_RESULT_TO_OUTCOME = {
    TxResult.OK: TransmitOutcome.ACKNOWLEDGED,
    TxResult.NO_SCOUT_ACK: TransmitOutcome.NOT_LISTENING,
    TxResult.NO_DATA_ACK: TransmitOutcome.HANDSHAKE_FAILED,
    TxResult.LINE_JAMMED: TransmitOutcome.LINE_JAMMED,
    TxResult.TIMEOUT: TransmitOutcome.TIMEOUT,
}


def tx_result_to_outcome(result: TxResult) -> TransmitOutcome:
    """Map a Piconet TX_RESULT to a transport-neutral TransmitOutcome.

    OK/NO_SCOUT_ACK/NO_DATA_ACK/LINE_JAMMED/TIMEOUT have direct equivalents;
    the firmware-anomaly results (OVERFLOW, UNDERRUN, MISC, UNEXPECTED,
    UNINITIALISED, INVALID_RECEIVE_ID) fold into NETWORK_ERROR.
    """
    return _TX_RESULT_TO_OUTCOME.get(result, TransmitOutcome.NETWORK_ERROR)

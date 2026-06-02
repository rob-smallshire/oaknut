"""Contract for Econet frame parsing and the EconetPacket <-> Piconet mapping."""

import base64

import pytest
from oaknut.econet.core import (
    Address,
    EconetError,
    EconetPacket,
    PacketKind,
    TransmitOutcome,
)
from oaknut.econet.piconet.mapping import (
    broadcast_command_for,
    econet_to_tx_command,
    event_to_econet,
    tx_result_to_outcome,
)
from oaknut.econet.piconet.protocol import (
    MonitorEvent,
    RxBroadcastEvent,
    RxImmediateEvent,
    RxTransmitEvent,
    StatusEvent,
    TxResult,
    TxResultEvent,
)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# -- inbound: events -> EconetPacket ---------------------------------


def test_broadcast_event_maps_to_a_broadcast_packet():
    frame = bytes([0xFF, 0xFF, 2, 0, 0x80, 0x99]) + b"hello"
    packet = event_to_econet(RxBroadcastEvent(frame=frame))
    assert packet.kind is PacketKind.BROADCAST
    assert packet.dst == Address(0xFF, 0xFF)
    assert packet.dst.is_broadcast
    assert packet.src == Address(0, 2)
    assert packet.control == 0x80
    assert packet.port == 0x99
    assert packet.payload == b"hello"


def test_transmit_event_maps_to_a_unicast_packet():
    scout = bytes([1, 0, 2, 0, 0x80, 0x99])
    data = bytes([1, 0, 2, 0]) + b"payload"
    packet = event_to_econet(RxTransmitEvent(reply_id=0, scout=scout, data=data))
    assert packet.kind is PacketKind.UNICAST
    assert packet.dst == Address(0, 1)
    assert packet.src == Address(0, 2)
    assert packet.control == 0x80  # raw Econet control byte, high bit intact
    assert packet.port == 0x99
    assert packet.payload == b"payload"


def test_transmit_event_with_port_zero_is_reclassified_as_immediate():
    scout = bytes([1, 0, 2, 0, 0x88, 0x00])
    data = bytes([1, 0, 2, 0])
    packet = event_to_econet(RxTransmitEvent(reply_id=0, scout=scout, data=data))
    assert packet.kind is PacketKind.IMMEDIATE
    assert packet.port == 0x00


def test_immediate_event_maps_to_an_immediate_packet():
    scout = bytes([1, 0, 2, 0, 0x88, 0x00])
    data = bytes([1, 0, 2, 0])
    packet = event_to_econet(RxImmediateEvent(scout=scout, data=data))
    assert packet.kind is PacketKind.IMMEDIATE
    assert packet.control == 0x88


def test_non_inbound_events_map_to_none():
    assert event_to_econet(TxResultEvent(TxResult.OK)) is None
    assert event_to_econet(StatusEvent("2.0.20", 1, 0xFF, 1)) is None
    assert event_to_econet(MonitorEvent(frame=b"\x01\x00\x02\x00")) is None


def test_short_frame_raises():
    with pytest.raises(EconetError):
        event_to_econet(RxBroadcastEvent(frame=b"\x01\x02"))


# -- outbound: EconetPacket -> commands ------------------------------


def test_econet_to_tx_command():
    packet = EconetPacket(
        PacketKind.UNICAST, Address(0, 254), Address(0, 1), control=0x80, port=0x99, payload=b"Hi"
    )
    assert econet_to_tx_command(packet) == f"TX 254 0 128 153 {_b64(b'Hi')}"


def test_broadcast_command_prefixes_control_and_port():
    line = broadcast_command_for(b"hi", port=0x99, control=0x80)
    assert line == f"BCAST {_b64(bytes([0x80, 0x99]) + b'hi')}"


@pytest.mark.parametrize(
    "result,outcome",
    [
        (TxResult.OK, TransmitOutcome.ACKNOWLEDGED),
        (TxResult.NO_SCOUT_ACK, TransmitOutcome.NOT_LISTENING),
        (TxResult.NO_DATA_ACK, TransmitOutcome.HANDSHAKE_FAILED),
        (TxResult.LINE_JAMMED, TransmitOutcome.LINE_JAMMED),
        (TxResult.TIMEOUT, TransmitOutcome.TIMEOUT),
        (TxResult.OVERFLOW, TransmitOutcome.NETWORK_ERROR),
        (TxResult.UNDERRUN, TransmitOutcome.NETWORK_ERROR),
        (TxResult.MISC, TransmitOutcome.NETWORK_ERROR),
        (TxResult.UNEXPECTED, TransmitOutcome.NETWORK_ERROR),
        (TxResult.UNINITIALISED, TransmitOutcome.NETWORK_ERROR),
    ],
)
def test_tx_result_to_outcome(result, outcome):
    assert tx_result_to_outcome(result) is outcome

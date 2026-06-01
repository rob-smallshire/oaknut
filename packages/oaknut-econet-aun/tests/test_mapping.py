"""Contract for the EconetPacket <-> AunPacket mapping."""

import pytest
from oaknut.econet.aun import AunPacket, AunType
from oaknut.econet.aun.mapping import (
    aun_to_econet,
    aun_type_for_kind,
    econet_to_aun,
    kind_for_aun_type,
)
from oaknut.econet.core import Address, EconetError, EconetPacket, PacketKind


@pytest.mark.parametrize(
    "kind,aun_type",
    [
        (PacketKind.BROADCAST, AunType.BROADCAST),
        (PacketKind.UNICAST, AunType.UNICAST),
        (PacketKind.IMMEDIATE, AunType.IMMEDIATE),
        (PacketKind.IMMEDIATE_REPLY, AunType.IMMEDIATE_REPLY),
    ],
)
def test_kind_and_type_are_a_bijection(kind, aun_type):
    assert aun_type_for_kind(kind) is aun_type
    assert kind_for_aun_type(aun_type) is kind


@pytest.mark.parametrize("aun_type", [AunType.ACK, AunType.NACK])
def test_ack_and_nack_have_no_logical_kind(aun_type):
    with pytest.raises(EconetError):
        kind_for_aun_type(aun_type)


def test_econet_to_aun_clears_the_control_high_bit():
    packet = EconetPacket(
        PacketKind.UNICAST, Address(0, 254), Address(0, 1), control=0x80, port=0x99, payload=b"x"
    )
    aun = econet_to_aun(packet, handle=8)
    assert aun.type is AunType.UNICAST
    assert aun.control == 0x00
    assert aun.port == 0x99
    assert aun.handle == 8
    assert aun.payload == b"x"


def test_econet_to_aun_preserves_low_control_bits():
    packet = EconetPacket(
        PacketKind.UNICAST, Address(0, 254), Address(0, 1), control=0x82, port=0x99
    )
    assert econet_to_aun(packet, handle=0).control == 0x02


def test_aun_to_econet_restores_control_high_bit_and_applies_addresses():
    aun = AunPacket(AunType.UNICAST, port=0x99, control=0x02, handle=12, payload=b"y")
    destination = Address(0, 1)
    source = Address(0, 254)
    packet = aun_to_econet(aun, dst=destination, src=source)
    assert packet.kind is PacketKind.UNICAST
    assert packet.control == 0x82
    assert packet.port == 0x99
    assert packet.dst == destination
    assert packet.src == source
    assert packet.seq == 12
    assert packet.payload == b"y"


def test_round_trip_preserves_the_logical_packet():
    original = EconetPacket(
        PacketKind.UNICAST, Address(0, 254), Address(0, 1), control=0x80, port=0x99, payload=b"data"
    )
    aun = econet_to_aun(original, handle=5)
    restored = aun_to_econet(aun, dst=original.dst, src=original.src)
    assert restored.kind == original.kind
    assert restored.control == original.control
    assert restored.port == original.port
    assert restored.payload == original.payload
    assert restored.dst == original.dst
    assert restored.src == original.src
    assert restored.seq == 5

"""Contract for PacketKind and EconetPacket."""

import dataclasses

import pytest
from oaknut.econet.core import Address, EconetPacket, PacketKind


def _addr(station):
    return Address(0, station)


def test_packet_kinds_exist():
    names = {kind.name for kind in PacketKind}
    assert {"BROADCAST", "UNICAST", "IMMEDIATE", "IMMEDIATE_REPLY"} <= names


def test_stores_fields():
    packet = EconetPacket(
        kind=PacketKind.UNICAST,
        dst=_addr(254),
        src=_addr(2),
        control=0x80,
        port=0x99,
        payload=b"hello",
    )
    assert packet.kind is PacketKind.UNICAST
    assert packet.dst == _addr(254)
    assert packet.src == _addr(2)
    assert packet.control == 0x80
    assert packet.port == 0x99
    assert packet.payload == b"hello"
    assert packet.seq is None


def test_payload_defaults_empty():
    packet = EconetPacket(PacketKind.BROADCAST, _addr(255), _addr(2), control=0, port=0x99)
    assert packet.payload == b""


@pytest.mark.parametrize("control", [-1, 256])
def test_rejects_out_of_range_control(control):
    with pytest.raises(ValueError):
        EconetPacket(PacketKind.UNICAST, _addr(254), _addr(2), control=control, port=0x99)


@pytest.mark.parametrize("port", [-1, 256])
def test_rejects_out_of_range_port(port):
    with pytest.raises(ValueError):
        EconetPacket(PacketKind.UNICAST, _addr(254), _addr(2), control=0x80, port=port)


def test_is_frozen():
    packet = EconetPacket(PacketKind.UNICAST, _addr(254), _addr(2), control=0x80, port=0x99)
    with pytest.raises(dataclasses.FrozenInstanceError):
        packet.control = 1


def test_equality_and_hashable():
    one = EconetPacket(
        PacketKind.UNICAST, _addr(254), _addr(2), control=0x80, port=0x99, payload=b"x"
    )
    two = EconetPacket(
        PacketKind.UNICAST, _addr(254), _addr(2), control=0x80, port=0x99, payload=b"x"
    )
    assert one == two
    assert hash(one) == hash(two)

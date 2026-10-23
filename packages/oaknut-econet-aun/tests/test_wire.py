"""Contract for the AUN wire codec (AunType, AunPacket)."""

import pytest
from oaknut.econet.aun import AunPacket, AunType
from oaknut.econet.core import EconetError


def test_aun_type_values():
    assert AunType.BROADCAST == 1
    assert AunType.UNICAST == 2
    assert AunType.ACK == 3
    assert AunType.NACK == 4
    assert AunType.IMMEDIATE == 5
    assert AunType.IMMEDIATE_REPLY == 6


def test_encode_known_vector():
    packet = AunPacket(AunType.UNICAST, port=0x99, control=0x80, handle=4, payload=b"Hi")
    assert packet.encode() == b"\x02\x99\x80\x00\x04\x00\x00\x00Hi"


def test_decode_known_vector():
    packet = AunPacket.decode(b"\x02\x99\x80\x00\x04\x00\x00\x00Hi")
    assert packet.type is AunType.UNICAST
    assert packet.port == 0x99
    assert packet.control == 0x80
    assert packet.handle == 4
    assert packet.payload == b"Hi"


def test_handle_is_little_endian_in_bytes_4_to_7():
    packet = AunPacket(AunType.UNICAST, port=0, control=0, handle=0x01020304)
    assert packet.encode()[4:8] == b"\x04\x03\x02\x01"


def test_pad_byte_is_zero():
    packet = AunPacket(AunType.ACK, port=0, control=0, handle=0)
    assert packet.encode()[3] == 0x00


@pytest.mark.parametrize("aun_type", list(AunType))
def test_round_trips_for_every_type(aun_type):
    original = AunPacket(aun_type, port=0x9C, control=0x82, handle=0xDEADBEEF, payload=b"\x01\x02\x03")
    assert AunPacket.decode(original.encode()) == original


def test_decode_header_only_has_empty_payload():
    packet = AunPacket.decode(b"\x03\x00\x00\x00\x00\x00\x00\x00")
    assert packet.type is AunType.ACK
    assert packet.payload == b""


def test_decode_rejects_short_buffer():
    with pytest.raises(EconetError):
        AunPacket.decode(b"\x02\x99\x80")


def test_decode_rejects_unknown_type():
    with pytest.raises(EconetError):
        AunPacket.decode(b"\x07\x00\x00\x00\x00\x00\x00\x00")


@pytest.mark.parametrize("port", [-1, 256])
def test_rejects_out_of_range_port(port):
    with pytest.raises(ValueError):
        AunPacket(AunType.UNICAST, port=port, control=0)


@pytest.mark.parametrize("control", [-1, 256])
def test_rejects_out_of_range_control(control):
    with pytest.raises(ValueError):
        AunPacket(AunType.UNICAST, port=0, control=control)


@pytest.mark.parametrize("handle", [-1, 0x1_0000_0000])
def test_rejects_out_of_range_handle(handle):
    with pytest.raises(ValueError):
        AunPacket(AunType.UNICAST, port=0, control=0, handle=handle)

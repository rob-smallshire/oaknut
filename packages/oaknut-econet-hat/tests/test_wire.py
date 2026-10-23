"""Contract for the kernel __econet_packet_aun struct codec."""

import pytest
from oaknut.econet.core import Address, EconetError
from oaknut.econet.hat.wire import KernelPacket, KernelPacketType, TxStatus


def test_packet_types():
    assert KernelPacketType.BROADCAST == 1
    assert KernelPacketType.DATA == 2
    assert KernelPacketType.ACK == 3
    assert KernelPacketType.NAK == 4
    assert KernelPacketType.IMMEDIATE == 5
    assert KernelPacketType.IMMEDIATE_REPLY == 6
    assert KernelPacketType.INK == 7


def test_tx_status_values():
    assert TxStatus.SUCCESS == 0x00
    assert TxStatus.JAMMED == 0x40
    assert TxStatus.HANDSHAKE_FAIL == 0x41
    assert TxStatus.NOT_LISTENING == 0x42
    assert TxStatus.NO_CLOCK == 0x43
    assert TxStatus.IN_PROGRESS == 0xFE


def test_encode_known_vector():
    packet = KernelPacket(
        KernelPacketType.DATA, Address(0, 254), Address(0, 1), control=0x80, port=0x99, seq=4, payload=b"Hi"
    )
    assert packet.encode() == b"\xfe\x00\x01\x00\x02\x99\x80\x00\x04\x00\x00\x00Hi"


def test_decode_known_vector():
    packet = KernelPacket.decode(b"\xfe\x00\x01\x00\x02\x99\x80\x00\x04\x00\x00\x00Hi")
    assert packet.ttype is KernelPacketType.DATA
    assert packet.dst == Address(0, 254)
    assert packet.src == Address(0, 1)
    assert packet.control == 0x80
    assert packet.port == 0x99
    assert packet.seq == 4
    assert packet.payload == b"Hi"


def test_seq_is_little_endian_at_bytes_8_to_11():
    packet = KernelPacket(
        KernelPacketType.DATA, Address(0, 1), Address(0, 2), control=0, port=0, seq=0x01020304
    )
    assert packet.encode()[8:12] == b"\x04\x03\x02\x01"


def test_control_high_bit_is_retained():
    packet = KernelPacket(KernelPacketType.DATA, Address(0, 1), Address(0, 2), control=0x82, port=0)
    assert packet.encode()[6] == 0x82


def test_padding_byte_is_zero():
    packet = KernelPacket(KernelPacketType.ACK, Address(0, 1), Address(0, 2), control=0, port=0)
    assert packet.encode()[7] == 0x00


@pytest.mark.parametrize("ttype", list(KernelPacketType))
def test_round_trips_for_every_type(ttype):
    original = KernelPacket(
        ttype, Address(1, 254), Address(2, 1), control=0x80, port=0x9C, seq=0xDEADBEEF, payload=b"\x01\x02"
    )
    assert KernelPacket.decode(original.encode()) == original


def test_decode_rejects_short_buffer():
    with pytest.raises(EconetError):
        KernelPacket.decode(b"\x01\x02\x03")


def test_decode_rejects_unknown_type():
    with pytest.raises(EconetError):
        KernelPacket.decode(b"\xfe\x00\x01\x00\x09\x99\x80\x00\x00\x00\x00\x00")


@pytest.mark.parametrize("control", [-1, 256])
def test_rejects_out_of_range_control(control):
    with pytest.raises(ValueError):
        KernelPacket(KernelPacketType.DATA, Address(0, 1), Address(0, 2), control=control, port=0)


@pytest.mark.parametrize("seq", [-1, 0x1_0000_0000])
def test_rejects_out_of_range_seq(seq):
    with pytest.raises(ValueError):
        KernelPacket(KernelPacketType.DATA, Address(0, 1), Address(0, 2), control=0, port=0, seq=seq)

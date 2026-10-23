"""Contract for the EconetPacket <-> KernelPacket mapping and station bitmap."""

import pytest
from oaknut.econet.core import (
    Address,
    EconetError,
    EconetPacket,
    PacketKind,
    TransmitOutcome,
)
from oaknut.econet.hat.mapping import (
    STATION_MAP_SIZE,
    econet_to_kernel,
    empty_station_map,
    is_in_progress,
    is_station_set,
    kernel_to_econet,
    set_station,
    tx_status_to_outcome,
)
from oaknut.econet.hat.wire import KernelPacket, KernelPacketType, TxStatus


@pytest.mark.parametrize(
    "kind,ttype",
    [
        (PacketKind.BROADCAST, KernelPacketType.BROADCAST),
        (PacketKind.UNICAST, KernelPacketType.DATA),
        (PacketKind.IMMEDIATE, KernelPacketType.IMMEDIATE),
        (PacketKind.IMMEDIATE_REPLY, KernelPacketType.IMMEDIATE_REPLY),
    ],
)
def test_kind_and_ttype_round_trip(kind, ttype):
    packet = EconetPacket(kind, Address(0, 254), Address(0, 1), control=0x80, port=0x99, payload=b"x")
    kernel = econet_to_kernel(packet, seq=7)
    assert kernel.ttype is ttype
    assert kernel.control == 0x80  # high bit retained
    assert kernel.seq == 7
    restored = kernel_to_econet(kernel)
    assert restored.kind is kind
    assert restored.dst == Address(0, 254)
    assert restored.src == Address(0, 1)
    assert restored.control == 0x80
    assert restored.port == 0x99
    assert restored.payload == b"x"
    assert restored.seq == 7


@pytest.mark.parametrize("ttype", [KernelPacketType.ACK, KernelPacketType.NAK, KernelPacketType.INK])
def test_handshake_artifacts_are_not_delivered(ttype):
    kernel = KernelPacket(ttype, Address(0, 1), Address(0, 2), control=0x80, port=0)
    assert kernel_to_econet(kernel) is None


# -- station-interest bitmap -----------------------------------------


def test_empty_station_map_is_all_zero():
    bitmap = empty_station_map()
    assert len(bitmap) == STATION_MAP_SIZE == 8192
    assert not any(bitmap)


def test_set_and_test_a_station():
    bitmap = empty_station_map()
    set_station(bitmap, Address(0, 2))
    assert is_station_set(bitmap, Address(0, 2))
    assert not is_station_set(bitmap, Address(0, 3))


def test_station_bit_index_matches_the_kernel_macro():
    bitmap = empty_station_map()
    set_station(bitmap, Address(0, 2))  # net 0, stn 2 -> byte net*32+stn//8=0, bit 1<<2
    assert bitmap[0] == 0b0000_0100


def test_stations_on_different_nets_are_independent():
    bitmap = empty_station_map()
    set_station(bitmap, Address(1, 254))
    assert is_station_set(bitmap, Address(1, 254))
    assert not is_station_set(bitmap, Address(0, 254))


# -- TX status -------------------------------------------------------


@pytest.mark.parametrize(
    "status,outcome",
    [
        (TxStatus.SUCCESS, TransmitOutcome.ACKNOWLEDGED),
        (TxStatus.NOT_LISTENING, TransmitOutcome.NOT_LISTENING),
        (TxStatus.NO_CLOCK, TransmitOutcome.NO_CLOCK),
        (TxStatus.JAMMED, TransmitOutcome.LINE_JAMMED),
        (TxStatus.HANDSHAKE_FAIL, TransmitOutcome.HANDSHAKE_FAILED),
        (TxStatus.UNDERRUN, TransmitOutcome.NETWORK_ERROR),
        (TxStatus.COLLISION, TransmitOutcome.NETWORK_ERROR),
    ],
)
def test_tx_status_to_outcome(status, outcome):
    assert tx_status_to_outcome(status) is outcome
    assert tx_status_to_outcome(int(status)) is outcome


def test_unknown_tx_status_is_network_error():
    assert tx_status_to_outcome(0x77) is TransmitOutcome.NETWORK_ERROR


def test_is_in_progress():
    assert is_in_progress(TxStatus.IN_PROGRESS)
    assert is_in_progress(TxStatus.DATA_PROGRESS)
    assert is_in_progress(TxStatus.START_WAIT)
    assert not is_in_progress(TxStatus.SUCCESS)
    assert not is_in_progress(TxStatus.NOT_LISTENING)


def test_econet_to_kernel_rejects_nothing_for_valid_kinds():
    # A sanity check that a normal unicast maps without error.
    packet = EconetPacket(PacketKind.UNICAST, Address(0, 254), Address(0, 1), control=0x80, port=0x99)
    assert isinstance(econet_to_kernel(packet), KernelPacket)


def test_kind_for_unknown_ttype_is_not_mapped():
    # decode-level guard already covers unknown bytes; here a handshake type.
    with pytest.raises(EconetError):
        from oaknut.econet.hat.mapping import kind_for_ttype

        kind_for_ttype(KernelPacketType.ACK)

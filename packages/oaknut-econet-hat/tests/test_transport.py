"""Integration tests for HatTransport driven by the in-process FakeKernelDevice."""

import asyncio

from oaknut.econet.core import (
    Address,
    EconetPacket,
    PacketKind,
    TransmitOutcome,
    TransportCapability,
)
from oaknut.econet.hat import FakeKernelDevice, HatTransport
from oaknut.econet.hat.mapping import is_station_set
from oaknut.econet.hat.wire import KernelPacket, KernelPacketType, TxStatus


def _unicast(dst_station=2, src_station=1, *, port=0x99, control=0x80, payload=b"hi"):
    return EconetPacket(
        PacketKind.UNICAST,
        Address(0, dst_station),
        Address(0, src_station),
        control=control,
        port=port,
        payload=payload,
    )


def test_capabilities_and_local_station():
    transport = HatTransport(device=FakeKernelDevice(), local_station=Address(0, 1))
    assert transport.capabilities == frozenset(
        {
            TransportCapability.BROADCAST,
            TransportCapability.MONITOR,
            TransportCapability.MULTI_NET,
        }
    )
    assert transport.local_station == Address(0, 1)


async def test_open_sets_the_local_station_in_the_interest_map():
    device = FakeKernelDevice()
    async with HatTransport(device=device, local_station=Address(0, 5)):
        pass
    assert device.station_maps  # SET_STATIONS was issued
    assert is_station_set(device.station_maps[-1], Address(0, 5))


async def test_transmit_is_acknowledged_and_encodes_the_packet():
    device = FakeKernelDevice()
    async with HatTransport(device=device, local_station=Address(0, 1)) as transport:
        result = await transport.transmit(_unicast(payload=b"hello"))
        assert result.acknowledged
        sent = KernelPacket.decode(device.transmitted[-1])
        assert sent.ttype is KernelPacketType.DATA
        assert sent.dst == Address(0, 2)
        assert sent.control == 0x80
        assert sent.payload == b"hello"


async def test_transmit_maps_a_scripted_failure():
    device = FakeKernelDevice()
    device.script_tx_status(TxStatus.NOT_LISTENING)
    async with HatTransport(device=device, local_station=Address(0, 1)) as transport:
        result = await transport.transmit(_unicast())
        assert result.outcome is TransmitOutcome.NOT_LISTENING


async def test_broadcast_sends_a_broadcast_packet_and_returns_none():
    device = FakeKernelDevice()
    async with HatTransport(device=device, local_station=Address(0, 1)) as transport:
        assert await transport.broadcast(b"hi", port=0x9C, control=0x82) is None
        sent = KernelPacket.decode(device.transmitted[-1])
        assert sent.ttype is KernelPacketType.BROADCAST
        assert sent.dst.is_broadcast


async def test_inbound_packet_is_delivered():
    device = FakeKernelDevice()
    async with HatTransport(device=device, local_station=Address(0, 1)) as transport:
        incoming = KernelPacket(
            KernelPacketType.DATA, Address(0, 1), Address(0, 2), control=0x80, port=0x99, payload=b"payload"
        )
        device.inject(incoming.encode())
        received = await asyncio.wait_for(anext(aiter(transport)), timeout=1.0)
        assert received.kind is PacketKind.UNICAST
        assert received.src == Address(0, 2)
        assert received.payload == b"payload"


async def test_immediate_is_acknowledged_with_no_reply():
    device = FakeKernelDevice()
    async with HatTransport(device=device, local_station=Address(0, 1)) as transport:
        immediate = EconetPacket(
            PacketKind.IMMEDIATE, Address(0, 2), Address(0, 1), control=0x88, port=0x00
        )
        result = await transport.immediate(immediate)
        assert result.acknowledged
        assert result.reply is None

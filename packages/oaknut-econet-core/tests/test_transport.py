"""Behavioural tests for the EconetTransport ABC and the TestTransport double."""

import pytest
from oaknut.econet.core import (
    Address,
    EconetPacket,
    EconetTransport,
    PacketKind,
    TestTransport,
    TransmitOutcome,
    TransmitResult,
    TransportCapability,
)


def _unicast(dst_station, src_station, *, port=0x99, control=0x80, payload=b"hi"):
    return EconetPacket(
        PacketKind.UNICAST,
        Address(0, dst_station),
        Address(0, src_station),
        control=control,
        port=port,
        payload=payload,
    )


def test_econet_transport_is_abstract():
    with pytest.raises(TypeError):
        EconetTransport(name="x")


def test_transport_kind_is_econet_transport():
    assert EconetTransport.kind() == "econet.transport"
    assert TestTransport.kind() == "econet.transport"


def test_test_transport_is_an_econet_transport():
    assert issubclass(TestTransport, EconetTransport)


def test_capabilities_and_local_station_accessors():
    transport = TestTransport(
        local_station=Address(0, 42),
        capabilities=frozenset({TransportCapability.BROADCAST}),
    )
    assert transport.local_station == Address(0, 42)
    assert transport.capabilities == frozenset({TransportCapability.BROADCAST})


async def test_async_context_manager_opens_and_closes():
    transport = TestTransport()
    assert not transport.is_open
    async with transport as opened:
        assert opened is transport
        assert transport.is_open
    assert transport.is_closed


async def test_transmit_is_acknowledged_by_default_and_records_the_packet():
    async with TestTransport() as transport:
        packet = _unicast(254, 2)
        result = await transport.transmit(packet)
        assert isinstance(result, TransmitResult)
        assert result.acknowledged
        assert transport.transmitted == [packet]


async def test_transmit_returns_scripted_outcomes_in_order():
    async with TestTransport() as transport:
        transport.script_results(
            TransmitResult(TransmitOutcome.NOT_LISTENING),
            TransmitResult(TransmitOutcome.ACKNOWLEDGED),
        )
        first = await transport.transmit(_unicast(254, 2))
        second = await transport.transmit(_unicast(254, 2))
        assert first.outcome is TransmitOutcome.NOT_LISTENING
        assert second.outcome is TransmitOutcome.ACKNOWLEDGED


async def test_broadcast_records_a_broadcast_packet():
    async with TestTransport(local_station=Address(0, 2)) as transport:
        await transport.broadcast(b"\x01\x02", port=0x9C, control=0x82)
        assert len(transport.broadcasts) == 1
        broadcast = transport.broadcasts[0]
        assert broadcast.kind is PacketKind.BROADCAST
        assert broadcast.dst.is_broadcast
        assert broadcast.port == 0x9C
        assert broadcast.control == 0x82
        assert broadcast.payload == b"\x01\x02"


async def test_immediate_returns_a_scripted_reply():
    async with TestTransport() as transport:
        reply = _unicast(2, 254, port=0x00, control=0x88, payload=b"\x01\x00\x00\x00")
        transport.script_immediate_replies(
            TransmitResult(TransmitOutcome.ACKNOWLEDGED, reply=reply)
        )
        request = _unicast(254, 2, port=0x00, control=0x88, payload=b"")
        result = await transport.immediate(request)
        assert result.acknowledged
        assert result.reply == reply
        assert transport.immediates == [request]


async def test_inbound_async_iteration_yields_fed_packets():
    async with TestTransport() as transport:
        one = _unicast(2, 254, payload=b"one")
        two = _unicast(2, 254, payload=b"two")
        transport.feed(one)
        transport.feed(two)
        received = []
        async for packet in transport:
            received.append(packet)
            if len(received) == 2:
                await transport.close()  # injects the sentinel that ends iteration
        assert received == [one, two]


async def test_paired_transports_deliver_transmits_to_the_peer():
    left = TestTransport(name="left", local_station=Address(0, 1))
    right = TestTransport(name="right", local_station=Address(0, 2))
    left.link(right)
    async with (
        left,
        right,
    ):
        packet = _unicast(2, 1, payload=b"ping")
        result = await left.transmit(packet)
        assert result.acknowledged
        received = await anext(aiter(right))
        assert received == packet

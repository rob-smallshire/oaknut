"""Integration tests for AunTransport over a 127.0.0.1 loopback.

Two real AunTransports are bound to ephemeral UDP ports and pointed at each
other, so transmits, acknowledgements, broadcasts, and inbound delivery exercise
the full asyncio datagram path.
"""

import asyncio

import pytest
from oaknut.econet.aun import AunTransport
from oaknut.econet.core import (
    Address,
    EconetPacket,
    PacketKind,
    TransmitOutcome,
    TransportCapability,
    TransportConfigurationError,
)
from oaknut.extension import create_extension, list_extensions, namespace_for


def _unicast(dst, src, *, port=0x99, control=0x80, payload=b"hi"):
    return EconetPacket(PacketKind.UNICAST, dst, src, control=control, port=port, payload=payload)


def test_capabilities():
    transport = AunTransport(local_station=Address(0, 1))
    assert transport.capabilities == frozenset(
        {
            TransportCapability.BROADCAST,
            TransportCapability.IMMEDIATE_REPLY,
            TransportCapability.MULTI_NET,
            TransportCapability.DISCOVERY,
        }
    )
    assert transport.local_station == Address(0, 1)


def test_registered_on_the_transport_axis():
    assert "aun" in list_extensions(namespace_for("econet.transport"))


def test_loadable_via_create_extension():
    transport = create_extension(
        "econet.transport",
        namespace_for("econet.transport"),
        "aun",
        local_station=Address(0, 1),
    )
    assert isinstance(transport, AunTransport)
    assert transport.local_station == Address(0, 1)
    assert transport.name == "aun"


async def test_unicast_transmit_is_acknowledged_and_delivered():
    alice = AunTransport(local_station=Address(0, 1), host="127.0.0.1", port=0)
    bob = AunTransport(local_station=Address(0, 2), host="127.0.0.1", port=0)
    async with (
        alice,
        bob,
    ):
        alice.add_peer(Address(0, 2), "127.0.0.1", bob.local_port)
        bob.add_peer(Address(0, 1), "127.0.0.1", alice.local_port)

        result = await alice.transmit(_unicast(Address(0, 2), Address(0, 1), payload=b"hello"))
        assert result.acknowledged

        received = await asyncio.wait_for(anext(aiter(bob)), timeout=1.0)
        assert received.kind is PacketKind.UNICAST
        assert received.src == Address(0, 1)
        assert received.dst == Address(0, 2)
        assert received.port == 0x99
        assert received.control == 0x80  # high bit restored on the receive side
        assert received.payload == b"hello"


async def test_broadcast_is_delivered_to_peers():
    alice = AunTransport(local_station=Address(0, 1), host="127.0.0.1", port=0)
    bob = AunTransport(local_station=Address(0, 2), host="127.0.0.1", port=0)
    async with (
        alice,
        bob,
    ):
        alice.add_peer(Address(0, 2), "127.0.0.1", bob.local_port)
        bob.add_peer(Address(0, 1), "127.0.0.1", alice.local_port)

        await alice.broadcast(b"\x01\x02", port=0x9C, control=0x82)

        received = await asyncio.wait_for(anext(aiter(bob)), timeout=1.0)
        assert received.kind is PacketKind.BROADCAST
        assert received.payload == b"\x01\x02"


async def test_transmit_to_unknown_peer_raises():
    alice = AunTransport(local_station=Address(0, 1), host="127.0.0.1", port=0)
    async with alice:
        with pytest.raises(TransportConfigurationError):
            await alice.transmit(_unicast(Address(0, 99), Address(0, 1)))


async def test_transmit_times_out_without_an_ack():
    alice = AunTransport(local_station=Address(0, 1), host="127.0.0.1", port=0, ack_timeout=0.05)
    async with alice:
        alice.add_peer(Address(0, 2), "127.0.0.1", 9)  # nothing listens on discard
        result = await alice.transmit(_unicast(Address(0, 2), Address(0, 1)))
        assert result.outcome is TransmitOutcome.TIMEOUT


async def test_immediate_times_out_without_a_reply():
    alice = AunTransport(local_station=Address(0, 1), host="127.0.0.1", port=0, ack_timeout=0.05)
    async with alice:
        alice.add_peer(Address(0, 2), "127.0.0.1", 9)
        immediate = EconetPacket(
            PacketKind.IMMEDIATE, Address(0, 2), Address(0, 1), control=0x88, port=0x00
        )
        result = await alice.immediate(immediate)
        assert result.outcome is TransmitOutcome.TIMEOUT

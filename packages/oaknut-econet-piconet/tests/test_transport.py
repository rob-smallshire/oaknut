"""Integration tests for PiconetTransport driven by the in-process FakePiconet."""

import asyncio
import base64

from oaknut.econet.core import (
    Address,
    EconetPacket,
    PacketKind,
    TransmitOutcome,
    TransportCapability,
)
from oaknut.econet.piconet import FakePiconet, PiconetTransport
from oaknut.econet.piconet.protocol import PiconetMode, TxResult


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


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
    transport = PiconetTransport(link=FakePiconet(), local_station=Address(0, 1))
    assert transport.capabilities == frozenset(
        {TransportCapability.BROADCAST, TransportCapability.MONITOR}
    )
    assert transport.local_station == Address(0, 1)


async def test_open_configures_station_and_listen_mode():
    fake = FakePiconet()
    async with PiconetTransport(link=fake, local_station=Address(0, 5)):
        pass
    assert "SET_STATION 5" in fake.commands
    assert f"SET_MODE {int(PiconetMode.LISTEN)}" in fake.commands


async def test_transmit_is_acknowledged_by_default():
    fake = FakePiconet()
    async with PiconetTransport(link=fake, local_station=Address(0, 1)) as transport:
        result = await transport.transmit(_unicast())
        assert result.acknowledged
        assert any(command.startswith("TX 2 0 128 153 ") for command in fake.commands)


async def test_transmit_maps_a_scripted_failure():
    fake = FakePiconet()
    fake.script_tx_results(TxResult.NO_SCOUT_ACK)
    async with PiconetTransport(link=fake, local_station=Address(0, 1)) as transport:
        result = await transport.transmit(_unicast())
        assert result.outcome is TransmitOutcome.NOT_LISTENING


async def test_broadcast_sends_bcast_and_returns_none():
    fake = FakePiconet()
    async with PiconetTransport(link=fake, local_station=Address(0, 1)) as transport:
        assert await transport.broadcast(b"hi", port=0x99, control=0x80) is None
        assert any(command.startswith("BCAST ") for command in fake.commands)


async def test_inbound_transmit_is_delivered():
    fake = FakePiconet()
    async with PiconetTransport(link=fake, local_station=Address(0, 1)) as transport:
        scout = bytes([1, 0, 2, 0, 0x80, 0x99])
        data = bytes([1, 0, 2, 0]) + b"payload"
        fake.inject(f"RX_TRANSMIT 0 {_b64(scout)} {_b64(data)}")
        received = await asyncio.wait_for(anext(aiter(transport)), timeout=1.0)
        assert received.kind is PacketKind.UNICAST
        assert received.src == Address(0, 2)
        assert received.port == 0x99
        assert received.payload == b"payload"


async def test_immediate_is_acknowledged_with_no_reply():
    fake = FakePiconet()
    async with PiconetTransport(link=fake, local_station=Address(0, 1)) as transport:
        immediate = EconetPacket(
            PacketKind.IMMEDIATE, Address(0, 2), Address(0, 1), control=0x88, port=0x00
        )
        result = await transport.immediate(immediate)
        assert result.acknowledged
        assert result.reply is None

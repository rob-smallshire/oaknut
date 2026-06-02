"""Contract for the Service abstraction and the Station service host."""

import asyncio

import pytest
from oaknut.econet.core import Address, EconetPacket, PacketKind, TestTransport
from oaknut.econet.station import Service, Station
from oaknut.extension import ExtensionError, namespace_for


class _RecordingService(Service):
    def __init__(self, ports, name="recording"):
        super().__init__(name=name)
        self._ports = frozenset(ports)
        self.handled: list[EconetPacket] = []

    @property
    def ports(self):
        return self._ports

    async def handle(self, request, station):
        self.handled.append(request)


class _EchoService(Service):
    def __init__(self, name="echo"):
        super().__init__(name=name)

    @property
    def ports(self):
        return frozenset({0x99})

    async def handle(self, request, station):
        await station.reply(request.src, port=0x90, control=0x80, payload=b"echo:" + request.payload)


def test_service_is_an_extension_on_the_service_axis():
    assert Service.kind() == "econet.service"
    assert namespace_for(Service.kind()) == "oaknut.econet.service"


def test_register_extension_rejects_an_unknown_service():
    station = Station(TestTransport(local_station=Address(0, 254)))
    with pytest.raises(ExtensionError):
        station.register_extension("no-such-service")


def _packet(port, *, dst=Address(0, 254), src=Address(0, 1), payload=b"hi"):
    return EconetPacket(PacketKind.UNICAST, dst, src, control=0x80, port=port, payload=payload)


async def _wait_until(predicate, *, timeout=1.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError("condition was not met within the timeout")
        await asyncio.sleep(0.005)


def test_register_rejects_a_duplicate_port():
    station = Station(TestTransport(local_station=Address(0, 254)))
    station.register(_RecordingService({0x99}))
    with pytest.raises(ValueError):
        station.register(_RecordingService({0x99}))


def test_address_defaults_to_the_transport_local_station():
    assert Station(TestTransport(local_station=Address(0, 254))).address == Address(0, 254)


def test_address_can_be_overridden():
    station = Station(TestTransport(local_station=Address(0, 254)), address=Address(0, 9))
    assert station.address == Address(0, 9)


async def test_dispatches_a_packet_to_the_service_for_its_port():
    transport = TestTransport(local_station=Address(0, 254))
    service = _RecordingService({0x99})
    station = Station(transport)
    station.register(service)
    async with transport:
        serve = asyncio.create_task(station.serve())
        transport.feed(_packet(0x99, payload=b"one"))
        await _wait_until(lambda: len(service.handled) == 1)
    await serve
    assert service.handled[0].payload == b"one"


async def test_ignores_packets_on_unregistered_ports():
    transport = TestTransport(local_station=Address(0, 254))
    service = _RecordingService({0x99})
    station = Station(transport)
    station.register(service)
    async with transport:
        serve = asyncio.create_task(station.serve())
        transport.feed(_packet(0xB0))
        await asyncio.sleep(0.02)
    await serve
    assert service.handled == []


async def test_reply_transmits_from_the_station_address():
    transport = TestTransport(local_station=Address(0, 254))
    station = Station(transport)
    async with transport:
        result = await station.reply(Address(0, 1), port=0x90, control=0x80, payload=b"pong")
    assert result.acknowledged
    sent = transport.transmitted[-1]
    assert sent.dst == Address(0, 1)
    assert sent.src == Address(0, 254)
    assert sent.port == 0x90
    assert sent.payload == b"pong"


async def test_a_service_replies_to_the_client_via_the_station():
    transport = TestTransport(local_station=Address(0, 254))
    station = Station(transport)
    station.register(_EchoService())
    async with transport:
        serve = asyncio.create_task(station.serve())
        transport.feed(_packet(0x99, src=Address(0, 1), payload=b"hi"))
        await _wait_until(lambda: any(p.port == 0x90 for p in transport.transmitted))
    await serve
    reply = transport.transmitted[-1]
    assert reply.dst == Address(0, 1)
    assert reply.payload == b"echo:hi"

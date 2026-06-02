"""End-to-end tests of the KV store over paired in-memory transports.

The client and a Station running the KvServer sit on two linked TestTransports,
so a full request -> dispatch -> reply round-trip runs entirely in memory.
"""

import asyncio

from oaknut.econet.core import Address, TestTransport
from oaknut.econet.kvstore import KvClient, KvServer
from oaknut.econet.kvstore.protocol import KV_REQUEST_PORT
from oaknut.econet.station import Station


def test_kvserver_claims_the_request_port():
    assert KV_REQUEST_PORT in KvServer().ports


async def test_kvstore_loads_as_a_service_plugin():
    station = Station(TestTransport(local_station=Address(0, 254)))
    service = station.register_extension("kvstore")
    assert isinstance(service, KvServer)


async def test_full_round_trip_over_paired_transports():
    client_transport = TestTransport(name="client", local_station=Address(0, 1))
    server_transport = TestTransport(name="server", local_station=Address(0, 254))
    client_transport.link(server_transport)

    station = Station(server_transport)
    station.register(KvServer())
    client = KvClient(client_transport, server=Address(0, 254))

    async with (
        client_transport,
        server_transport,
    ):
        serve = asyncio.create_task(station.serve())
        async with asyncio.timeout(2.0):
            await client.put(b"colour", b"blue")
            assert await client.get(b"colour") == b"blue"
            assert await client.get(b"missing") is None
            assert await client.delete(b"colour") is True
            assert await client.get(b"colour") is None
            assert await client.delete(b"colour") is False
    await serve

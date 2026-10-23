"""Opt-in Piconet hardware tests, skipped unless a board is attached.

Set ``OAKNUT_PICONET_PORT`` to a serial device (e.g. ``/dev/ttyACM0``) to run
the bare-Pico tier (the control protocol only — no Econet needed). Additionally
set ``OAKNUT_PICONET_PEER`` to a ``net.stn`` address to run the on-Econet tier,
which needs a clocked Econet (e.g. a Pi HAT / PiEconetBridge supplying the
clock) and a peer station. Requires the ``serial`` extra (pyserial-asyncio).
"""

import os

import pytest
from oaknut.econet.core import Address, EconetPacket, PacketKind
from oaknut.econet.piconet import PiconetTransport, SerialPicoLink

_PORT = os.environ.get("OAKNUT_PICONET_PORT")
_PEER = os.environ.get("OAKNUT_PICONET_PEER")

pytestmark = pytest.mark.skipif(
    _PORT is None, reason="set OAKNUT_PICONET_PORT to run Piconet hardware tests"
)


async def test_status_round_trip_on_real_board():
    link = SerialPicoLink(port=_PORT)
    async with PiconetTransport(link=link, local_station=Address(0, 1)) as transport:
        status = await transport.status()
        assert status.version  # the firmware reported a version string


@pytest.mark.skipif(_PEER is None, reason="set OAKNUT_PICONET_PEER (net.stn) for on-Econet tests")
async def test_transmit_to_a_peer_over_econet():
    network, station = (int(part) for part in _PEER.split("."))
    link = SerialPicoLink(port=_PORT)
    async with PiconetTransport(link=link, local_station=Address(0, 1)) as transport:
        result = await transport.transmit(
            EconetPacket(
                PacketKind.UNICAST,
                Address(network, station),
                Address(0, 1),
                control=0x80,
                port=0x99,
                payload=b"oaknut",
            )
        )
        assert result.outcome is not None

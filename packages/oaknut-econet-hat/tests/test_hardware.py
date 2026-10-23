"""Opt-in PiEconetHAT hardware tests, skipped unless the device is present.

Set ``OAKNUT_ECONET_GPIO`` to the character device (e.g. ``/dev/econet-gpio``)
on a Linux host with the econet-gpio module loaded and the HAT fitted, to run
the open/close tier. Additionally set ``OAKNUT_ECONET_PEER`` to a ``net.stn``
address (with a clocked Econet and a peer station present) to run the transmit
tier.
"""

import os

import pytest
from oaknut.econet.core import Address, EconetPacket, PacketKind
from oaknut.econet.hat import HatTransport
from oaknut.econet.hat.gpio import EconetGpioDevice

_DEVICE = os.environ.get("OAKNUT_ECONET_GPIO")
_PEER = os.environ.get("OAKNUT_ECONET_PEER")

pytestmark = pytest.mark.skipif(
    _DEVICE is None, reason="set OAKNUT_ECONET_GPIO to run HAT hardware tests"
)


async def test_open_and_close_on_the_real_device():
    device = EconetGpioDevice(path=_DEVICE)
    async with HatTransport(device=device, local_station=Address(0, 1)):
        pass  # opening resets the module, enables AUN mode, sets the station map


@pytest.mark.skipif(_PEER is None, reason="set OAKNUT_ECONET_PEER (net.stn) for the transmit tier")
async def test_transmit_to_a_peer_over_econet():
    network, station = (int(part) for part in _PEER.split("."))
    device = EconetGpioDevice(path=_DEVICE)
    async with HatTransport(device=device, local_station=Address(0, 1)) as transport:
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

"""Run the core EconetTransport conformance suite against AunTransport.

The transmit/immediate contract checks address station 254, so the transport is
given a route to a dead UDP port: the checks then resolve as TIMEOUT (a valid
TransmitResult) rather than erroring, exercising the real datagram path.
"""

from oaknut.econet.aun import AunTransport
from oaknut.econet.core import Address
from oaknut.econet.core.conformance import EconetTransportConformance


class TestAunConformance(EconetTransportConformance):
    def make_transport(self):
        transport = AunTransport(
            local_station=Address(0, 1), host="127.0.0.1", port=0, ack_timeout=0.05
        )
        transport.add_peer(Address(0, 254), "127.0.0.1", 9)
        return transport

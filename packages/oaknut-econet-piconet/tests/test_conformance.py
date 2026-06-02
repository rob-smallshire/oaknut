"""Run the core EconetTransport conformance suite against PiconetTransport.

The transport is driven by the in-process FakePiconet, which acknowledges
transmits by default, so the contract checks resolve with no hardware.
"""

from oaknut.econet.core import Address
from oaknut.econet.core.conformance import EconetTransportConformance
from oaknut.econet.piconet import FakePiconet, PiconetTransport


class TestPiconetConformance(EconetTransportConformance):
    def make_transport(self):
        return PiconetTransport(link=FakePiconet(), local_station=Address(0, 1))

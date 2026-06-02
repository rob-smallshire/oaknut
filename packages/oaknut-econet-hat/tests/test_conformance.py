"""Run the core EconetTransport conformance suite against HatTransport.

Driven by the in-process FakeKernelDevice, which acknowledges transmits by
default, so the contract checks resolve with no hardware.
"""

from oaknut.econet.core import Address
from oaknut.econet.core.conformance import EconetTransportConformance
from oaknut.econet.hat import FakeKernelDevice, HatTransport


class TestHatConformance(EconetTransportConformance):
    def make_transport(self):
        return HatTransport(device=FakeKernelDevice(), local_station=Address(0, 1))

"""Run the reusable EconetTransport conformance suite against TestTransport.

This both validates TestTransport and exercises the conformance harness itself,
which the AUN/Piconet/HAT transport packages will reuse.
"""

from oaknut.econet.core import Address, TestTransport
from oaknut.econet.core.conformance import EconetTransportConformance


class TestLoopbackConformance(EconetTransportConformance):
    def make_transport(self):
        return TestTransport(local_station=Address(0, 1))

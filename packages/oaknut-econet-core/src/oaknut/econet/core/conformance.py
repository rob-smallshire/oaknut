"""A reusable conformance suite for EconetTransport implementations.

Subclass :class:`EconetTransportConformance` in a transport package's test
suite, implement :meth:`make_transport`, and pytest will run the inherited
contract checks against your transport. The checks assert the *shape* of the
contract — types and lifecycle — not transport-specific outcomes, so they hold
for any transport (the in-process :class:`TestTransport`, AUN, Piconet, the
HAT).

This module deliberately imports no test framework, so it is safe to import
anywhere; the concrete subclass lives in a test module that pytest collects.
"""

from __future__ import annotations

from oaknut.econet.core.addressing import Address
from oaknut.econet.core.capability import TransportCapability
from oaknut.econet.core.outcome import TransmitOutcome, TransmitResult
from oaknut.econet.core.packet import EconetPacket, PacketKind
from oaknut.econet.core.transport import EconetTransport


class EconetTransportConformance:
    """The contract every :class:`EconetTransport` implementation must satisfy.

    Concrete subclasses implement :meth:`make_transport` to return a fresh,
    unopened transport set up so that a unicast transmit resolves promptly. For
    the loopback :class:`TestTransport` that is automatic; a real transport's
    test subclass wires it to a controllable peer.
    """

    def make_transport(self) -> EconetTransport:
        """Return a fresh, unopened transport to exercise. Override this."""
        raise NotImplementedError

    @staticmethod
    def _unicast() -> EconetPacket:
        return EconetPacket(
            PacketKind.UNICAST,
            Address(0, 254),
            Address(0, 1),
            control=0x80,
            port=0x99,
            payload=b"conformance",
        )

    def test_kind_is_econet_transport(self):
        assert type(self.make_transport()).kind() == "econet.transport"

    def test_capabilities_is_a_frozenset_of_capabilities(self):
        capabilities = self.make_transport().capabilities
        assert isinstance(capabilities, frozenset)
        assert all(isinstance(capability, TransportCapability) for capability in capabilities)

    def test_local_station_is_address_or_none(self):
        local_station = self.make_transport().local_station
        assert local_station is None or isinstance(local_station, Address)

    async def test_context_manager_yields_self(self):
        transport = self.make_transport()
        async with transport as entered:
            assert entered is transport

    async def test_transmit_returns_a_transmit_result(self):
        async with self.make_transport() as transport:
            result = await transport.transmit(self._unicast())
            assert isinstance(result, TransmitResult)
            assert isinstance(result.outcome, TransmitOutcome)

    async def test_immediate_returns_a_transmit_result(self):
        async with self.make_transport() as transport:
            immediate = EconetPacket(
                PacketKind.IMMEDIATE,
                Address(0, 254),
                Address(0, 1),
                control=0x88,
                port=0x00,
            )
            result = await transport.immediate(immediate)
            assert isinstance(result, TransmitResult)
            assert isinstance(result.outcome, TransmitOutcome)

    async def test_broadcast_when_supported_does_not_raise(self):
        async with self.make_transport() as transport:
            if TransportCapability.BROADCAST not in transport.capabilities:
                return
            assert await transport.broadcast(b"\x00", port=0x9C, control=0x82) is None

    async def test_inbound_iteration_stops_after_close(self):
        transport = self.make_transport()
        async with transport:
            pass
        received = [packet async for packet in transport]
        assert received == []

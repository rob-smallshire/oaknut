"""Core abstractions for Econet networking in the oaknut family.

This package is the foundation of the ``oaknut-econet-*`` family. It defines
the logical-packet currency every transport speaks and the abstract interface
every transport implements:

- :class:`Address` — ``(network, station)`` addressing.
- :class:`EconetPacket` / :class:`PacketKind` — the AUN-modelled logical packet.
- :class:`TransmitResult` / :class:`TransmitOutcome` — delivery outcomes.
- :class:`EconetTransport` — the ``asyncio``-native transport interface, with
  :class:`TransportCapability` flags.
- :class:`TestTransport` — an in-process loopback transport for hardware-free
  testing.

The abstraction sits at the *logical-packet* level: the Econet four-way
handshake (scout / scout-ack / data / final-ack) is resolved below the
transport boundary, so callers work in whole packets rather than ADLC frames.
See ``docs/dev/econet-design.md`` for the design rationale.

Concrete transports (AUN, Piconet, PiEconetHAT) live in sibling distributions
and register on the ``oaknut.econet.transport`` extension axis.
"""

__version__ = "12.5.3"

__all__: list[str] = []

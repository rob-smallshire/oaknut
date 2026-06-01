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

from __future__ import annotations

from oaknut.econet.core.addressing import (
    BROADCAST_ADDRESS,
    BROADCAST_STATION,
    IMMEDIATE_PORT,
    LOCAL_NET,
    Address,
)
from oaknut.econet.core.capability import TransportCapability
from oaknut.econet.core.outcome import TransmitOutcome, TransmitResult
from oaknut.econet.core.packet import EconetPacket, PacketKind

__version__ = "12.5.3"

__all__ = [
    "Address",
    "BROADCAST_ADDRESS",
    "BROADCAST_STATION",
    "EconetPacket",
    "IMMEDIATE_PORT",
    "LOCAL_NET",
    "PacketKind",
    "TransmitOutcome",
    "TransmitResult",
    "TransportCapability",
]

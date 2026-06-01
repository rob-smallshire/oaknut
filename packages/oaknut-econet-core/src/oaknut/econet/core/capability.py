"""Capability flags describing what a transport supports."""

from __future__ import annotations

from enum import Enum, auto


class TransportCapability(Enum):
    """A feature a transport may or may not provide.

    Applications branch on capabilities rather than on transport identity
    (never ``isinstance(transport, AunTransport)``). A transport exposes the
    set it supports via :attr:`EconetTransport.capabilities`.
    """

    #: Promiscuous receive of all traffic on the segment, not just our station.
    MONITOR = auto()
    #: Can send host-generated replies to inbound immediate operations.
    IMMEDIATE_REPLY = auto()
    #: Can originate broadcasts.
    BROADCAST = auto()
    #: Honours network numbers beyond the local net.
    MULTI_NET = auto()
    #: Participates in mDNS advertise/discover.
    DISCOVERY = auto()

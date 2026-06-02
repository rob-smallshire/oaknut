"""Econet addressing: the (network, station) pair and well-known values."""

from __future__ import annotations

from dataclasses import dataclass

#: Station number reserved for broadcasts (0xFF). A frame addressed to this
#: station is delivered to every listening station on the segment.
BROADCAST_STATION = 0xFF

#: Network number meaning "this network" — the local Econet segment. A frame
#: addressed with network 0 stays on the segment it was sent from.
LOCAL_NET = 0x00

#: The port carrying immediate operations (PEEK, POKE, JSR, MachinePeek, ...).
#: Port 0 is not a normal data port; it is serviced by the receiver's NMI.
IMMEDIATE_PORT = 0x00

_BYTE_RANGE = range(0x00, 0x100)


@dataclass(frozen=True, slots=True)
class Address:
    """An Econet station address: an 8-bit network and 8-bit station number.

    Network ``0`` (:data:`LOCAL_NET`) means "this network". Station ``255``
    (:data:`BROADCAST_STATION`) is the broadcast station.
    """

    network: int
    station: int

    def __post_init__(self) -> None:
        if self.network not in _BYTE_RANGE:
            raise ValueError(f"network must be 0..255, got {self.network!r}")
        if self.station not in _BYTE_RANGE:
            raise ValueError(f"station must be 0..255, got {self.station!r}")

    @property
    def is_broadcast(self) -> bool:
        """True if this addresses the broadcast station."""
        return self.station == BROADCAST_STATION

    @property
    def is_local_net(self) -> bool:
        """True if the network is the local segment (network 0)."""
        return self.network == LOCAL_NET

    @classmethod
    def parse(cls, text: str) -> Address:
        """Parse a ``"net.station"`` string (e.g. ``"0.254"``), the inverse of str()."""
        network, separator, station = text.partition(".")
        if separator != "." or not network or not station:
            raise ValueError(f"address must be 'net.station', got {text!r}")
        try:
            return cls(int(network), int(station))
        except ValueError as exc:
            raise ValueError(f"invalid address {text!r}: {exc}") from exc

    def __str__(self) -> str:
        return f"{self.network}.{self.station}"


#: The full broadcast address, 255.255.
BROADCAST_ADDRESS = Address(network=0xFF, station=BROADCAST_STATION)

"""The KernelDevice seam: a packet channel to the econet-gpio kernel module.

HatTransport works through this interface, so it is agnostic to whether the
module is real (:class:`EconetGpioDevice`, the ``/dev/econet-gpio`` char device)
or simulated (:class:`FakeKernelDevice`). Packets cross the seam as the raw
``struct __econet_packet_aun`` bytes; a transmit returns the final kernel TX
status (an ``ECONET_TX_*`` integer).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class KernelDevice(ABC):
    """A packet-oriented channel to the econet-gpio kernel module."""

    @abstractmethod
    async def open(self) -> None:
        """Open the device and enable AUN (four-way) mode."""

    @abstractmethod
    async def close(self) -> None:
        """Close the device and end inbound iteration."""

    @abstractmethod
    async def set_stations(self, bitmap: bytes) -> None:
        """Load the station-interest bitmap (the SET_STATIONS ioctl)."""

    @abstractmethod
    async def transmit(self, packet: bytes) -> int:
        """Write one packet and return its final ECONET_TX_* status."""

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[bytes]:
        """Iterate raw inbound packets received from the wire."""

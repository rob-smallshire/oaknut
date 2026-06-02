"""The PicoLink seam: a bidirectional line channel to a Piconet board.

The transport sends command lines and consumes event lines through this
interface, so it is agnostic to whether the board is real (a USB serial port,
:class:`SerialPicoLink`) or simulated (:class:`FakePiconet`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class PicoLink(ABC):
    """A line-oriented, bidirectional channel to a Piconet board."""

    @abstractmethod
    async def open(self) -> None:
        """Open the channel."""

    @abstractmethod
    async def close(self) -> None:
        """Close the channel and end inbound line iteration."""

    @abstractmethod
    async def send_line(self, line: str) -> None:
        """Send one command line to the board (the terminator is added here)."""

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[str]:
        """Iterate event lines received from the board."""

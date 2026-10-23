"""FakeKernelDevice — an in-process simulation of /dev/econet-gpio.

It implements :class:`KernelDevice` in memory: ``transmit`` records the packet
and returns a scriptable TX status (``SUCCESS`` by default), ``set_stations``
records the bitmap, and tests inject inbound packets with :meth:`inject`.
Shipped in the package (not test-only) so the transport is exercisable in CI
with no hardware, and downstream code can test against it too.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator

from oaknut.econet.hat.device import KernelDevice
from oaknut.econet.hat.wire import TxStatus


class _Closed:
    """Sentinel queued by close() to end inbound iteration."""


_CLOSED = _Closed()


class FakeKernelDevice(KernelDevice):
    """An in-memory KernelDevice simulating the econet-gpio module."""

    def __init__(self) -> None:
        self._inbound: asyncio.Queue = asyncio.Queue()
        self._tx_status: deque[int] = deque()
        self._closed = False
        self.transmitted: list[bytes] = []
        self.station_maps: list[bytes] = []

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._inbound.put_nowait(_CLOSED)

    async def set_stations(self, bitmap: bytes) -> None:
        self.station_maps.append(bytes(bitmap))

    async def transmit(self, packet: bytes) -> int:
        self.transmitted.append(bytes(packet))
        status = self._tx_status.popleft() if self._tx_status else TxStatus.SUCCESS
        return int(status)

    def inject(self, packet: bytes) -> None:
        """Deliver *packet* (raw kernel bytes) as if received from the wire."""
        self._inbound.put_nowait(bytes(packet))

    def script_tx_status(self, *statuses: TxStatus | int) -> None:
        """Queue the TX statuses the next transmits will return, in order."""
        self._tx_status.extend(int(status) for status in statuses)

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        item = await self._inbound.get()
        if item is _CLOSED:
            raise StopAsyncIteration
        return item

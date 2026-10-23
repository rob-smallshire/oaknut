"""FakePiconet — an in-process simulation of the Pico firmware.

It implements :class:`PicoLink` by interpreting the command lines the transport
sends and emitting plausible event lines back, so the whole transport stack is
exercisable in CI with no hardware. Tests can script TX outcomes and inject
inbound RX event lines. Shipped in the package (not test-only) so downstream
code can test against it too.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator

from oaknut.econet.piconet.link import PicoLink
from oaknut.econet.piconet.protocol import PiconetMode, TxResult


class _Closed:
    """Sentinel queued by close() to end inbound iteration."""


_CLOSED = _Closed()


class FakePiconet(PicoLink):
    """An in-memory PicoLink simulating the Piconet firmware.

    Answers ``STATUS``, records ``SET_STATION``/``SET_MODE``, and replies to
    ``TX``/``BCAST`` with a ``TX_RESULT`` (``OK`` by default, or the next value
    queued by :meth:`script_tx_results`). Use :meth:`inject` to deliver an
    inbound event line (e.g. an ``RX_TRANSMIT``). Sent commands are recorded on
    :attr:`commands`.
    """

    def __init__(
        self,
        *,
        version: str = "2.0.20",
        station: int = 0,
        mode: PiconetMode = PiconetMode.STOP,
    ) -> None:
        self._inbound: asyncio.Queue = asyncio.Queue()
        self._version = version
        self._station = station
        self._mode = mode
        self._tx_results: deque[str] = deque()
        self._closed = False
        self.commands: list[str] = []

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._inbound.put_nowait(_CLOSED)

    async def send_line(self, line: str) -> None:
        self.commands.append(line)
        keyword, _, rest = line.partition(" ")
        if keyword == "STATUS":
            self._emit(f"STATUS {self._version} {self._station} 0xff {int(self._mode)}")
        elif keyword == "SET_STATION" and rest:
            self._station = int(rest)
        elif keyword == "SET_MODE" and rest:
            self._mode = PiconetMode(int(rest))
        elif keyword in ("TX", "BCAST"):
            result = self._tx_results.popleft() if self._tx_results else "OK"
            self._emit(f"TX_RESULT {result}")

    def inject(self, line: str) -> None:
        """Deliver *line* to the transport as if the board had emitted it."""
        self._inbound.put_nowait(line)

    def script_tx_results(self, *results: TxResult | str) -> None:
        """Queue the TX_RESULT values the next TX/BCAST commands will return."""
        for result in results:
            self._tx_results.append(result.value if isinstance(result, TxResult) else result)

    def _emit(self, line: str) -> None:
        self._inbound.put_nowait(line)

    def __aiter__(self) -> AsyncIterator[str]:
        return self

    async def __anext__(self) -> str:
        item = await self._inbound.get()
        if item is _CLOSED:
            raise StopAsyncIteration
        return item

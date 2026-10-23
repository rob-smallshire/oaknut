"""An in-process loopback EconetTransport for hardware-free testing."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator

from oaknut.econet.core.addressing import BROADCAST_ADDRESS, Address
from oaknut.econet.core.capability import TransportCapability
from oaknut.econet.core.outcome import TransmitOutcome, TransmitResult
from oaknut.econet.core.packet import EconetPacket, PacketKind
from oaknut.econet.core.transport import EconetTransport

_DEFAULT_CAPABILITIES = frozenset(
    {TransportCapability.BROADCAST, TransportCapability.IMMEDIATE_REPLY}
)


class _Closed:
    """Sentinel queued by close() to terminate inbound iteration."""


_CLOSED = _Closed()


class TestTransport(EconetTransport):
    """An in-process EconetTransport for testing applications without hardware.

    Two ways to use it:

    - *Standalone*: script transmit/immediate outcomes with
      :meth:`script_results` / :meth:`script_immediate_replies`, inject inbound
      packets with :meth:`feed`, and inspect :attr:`transmitted`,
      :attr:`broadcasts`, and :attr:`immediates`.
    - *Paired*: :meth:`link` two transports so each one's transmits and
      broadcasts arrive as inbound packets on the other — a toy client and
      server talking entirely in memory.
    """

    # Despite the "Test" prefix this is a helper, not a pytest test case.
    __test__ = False

    def __init__(
        self,
        name: str = "test",
        *,
        local_station: Address | None = None,
        capabilities: frozenset[TransportCapability] | None = None,
        default_outcome: TransmitOutcome = TransmitOutcome.ACKNOWLEDGED,
    ) -> None:
        super().__init__(name=name)
        self._local_station = local_station
        self._capabilities = (
            _DEFAULT_CAPABILITIES if capabilities is None else frozenset(capabilities)
        )
        self._default_outcome = default_outcome
        self._inbound: asyncio.Queue = asyncio.Queue()
        self._peer: TestTransport | None = None
        self._opened = False
        self._closed = False
        self._scripted_results: deque[TransmitResult] = deque()
        self._scripted_immediate_replies: deque[TransmitResult] = deque()
        self.transmitted: list[EconetPacket] = []
        self.broadcasts: list[EconetPacket] = []
        self.immediates: list[EconetPacket] = []

    # -- introspection -------------------------------------------------

    @property
    def capabilities(self) -> frozenset[TransportCapability]:
        return self._capabilities

    @property
    def local_station(self) -> Address | None:
        return self._local_station

    @property
    def is_open(self) -> bool:
        return self._opened and not self._closed

    @property
    def is_closed(self) -> bool:
        return self._closed

    # -- lifecycle -----------------------------------------------------

    async def open(self) -> None:
        self._opened = True

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._inbound.put_nowait(_CLOSED)

    # -- outbound ------------------------------------------------------

    async def transmit(self, packet: EconetPacket) -> TransmitResult:
        self.transmitted.append(packet)
        if self._peer is not None:
            self._peer.feed(packet)
        if self._scripted_results:
            return self._scripted_results.popleft()
        return TransmitResult(self._default_outcome)

    async def broadcast(self, payload: bytes, *, port: int, control: int) -> None:
        source = self._local_station or Address(0, 0)
        packet = EconetPacket(
            PacketKind.BROADCAST,
            BROADCAST_ADDRESS,
            source,
            control=control,
            port=port,
            payload=payload,
        )
        self.broadcasts.append(packet)
        if self._peer is not None:
            self._peer.feed(packet)

    async def immediate(self, packet: EconetPacket) -> TransmitResult:
        self.immediates.append(packet)
        if self._scripted_immediate_replies:
            return self._scripted_immediate_replies.popleft()
        return TransmitResult(self._default_outcome)

    # -- inbound -------------------------------------------------------

    def __aiter__(self) -> AsyncIterator[EconetPacket]:
        return self

    async def __anext__(self) -> EconetPacket:
        item = await self._inbound.get()
        if item is _CLOSED:
            raise StopAsyncIteration
        return item

    # -- test helpers --------------------------------------------------

    def feed(self, packet: EconetPacket) -> None:
        """Inject *packet* as an inbound packet for iteration."""
        self._inbound.put_nowait(packet)

    def script_results(self, *results: TransmitResult) -> None:
        """Queue the results :meth:`transmit` will return, in order."""
        self._scripted_results.extend(results)

    def script_immediate_replies(self, *results: TransmitResult) -> None:
        """Queue the results :meth:`immediate` will return, in order."""
        self._scripted_immediate_replies.extend(results)

    def link(self, other: TestTransport) -> None:
        """Cross-wire two transports so each delivers to the other's inbound."""
        self._peer = other
        other._peer = self

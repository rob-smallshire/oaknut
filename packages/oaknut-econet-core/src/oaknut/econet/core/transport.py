"""The abstract EconetTransport interface."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator

from oaknut.econet.core.addressing import Address
from oaknut.econet.core.capability import TransportCapability
from oaknut.econet.core.outcome import TransmitResult
from oaknut.econet.core.packet import EconetPacket
from oaknut.extension import Extension


class EconetTransport(Extension):
    """An asyncio-native conduit for logical Econet packets over one segment.

    A transport is the boundary between this host and a single Econet or AUN
    segment. It carries whole :class:`EconetPacket` s — the four-way handshake
    is resolved below it — and presents a *pull* interface: callers await
    :meth:`transmit` / :meth:`immediate` and iterate inbound packets with
    ``async for packet in transport``.

    Conceptually it is to Econet packets what :class:`asyncio.Transport` is to
    bytes, one layer up. Concrete transports plug in on the
    ``oaknut.econet.transport`` extension axis and differ in real ways —
    expressed as :class:`TransportCapability` flags, never by type checks.
    """

    @classmethod
    def _kind(cls) -> str:
        return "econet.transport"

    @classmethod
    def from_config(cls, *, name: str, address: Address | None, config: dict) -> EconetTransport:
        """Build a transport from a host config table.

        The default treats *config* as flat constructor keyword arguments (with
        hyphenated keys mapped to underscores) and supplies *address* as the
        ``local_station``. Transports with structured config (an AUN peer map,
        a serial port) override this.
        """
        kwargs = {key.replace("-", "_"): value for key, value in config.items()}
        return cls(name=name, local_station=address, **kwargs)

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[TransportCapability]:
        """The set of capabilities this transport supports."""

    @property
    @abstractmethod
    def local_station(self) -> Address | None:
        """This transport's own station address, if it has one."""

    @abstractmethod
    async def open(self) -> None:
        """Open the underlying endpoint."""

    @abstractmethod
    async def close(self) -> None:
        """Close the underlying endpoint and end inbound iteration."""

    async def __aenter__(self) -> EconetTransport:
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    @abstractmethod
    async def transmit(self, packet: EconetPacket) -> TransmitResult:
        """Send a reliable four-way unicast and await its outcome."""

    @abstractmethod
    async def broadcast(self, payload: bytes, *, port: int, control: int) -> None:
        """Send a fire-and-forget broadcast to the broadcast station."""

    @abstractmethod
    async def immediate(self, packet: EconetPacket) -> TransmitResult:
        """Perform a two-way immediate operation; any reply is on the result."""

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[EconetPacket]:
        """Iterate inbound packets (already acknowledged at the wire level)."""

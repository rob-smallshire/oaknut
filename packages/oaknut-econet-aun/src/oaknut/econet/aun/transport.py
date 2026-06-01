"""AunTransport — an EconetTransport over an asyncio UDP datagram endpoint."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from oaknut.econet.aun.mapping import aun_to_econet, econet_to_aun
from oaknut.econet.aun.wire import AunPacket, AunType
from oaknut.econet.core import (
    Address,
    EconetError,
    EconetPacket,
    EconetTransport,
    TransmitOutcome,
    TransmitResult,
    TransportCapability,
    TransportConfigurationError,
)

#: Conventional AUN UDP port; configurable per deployment.
DEFAULT_AUN_PORT = 32768

_HANDLE_MODULUS = 0x1_0000_0000


class _Closed:
    """Sentinel queued by close() to terminate inbound iteration."""


_CLOSED = _Closed()


class _AunProtocol(asyncio.DatagramProtocol):
    """Bridges asyncio's push datagram callbacks to the AunTransport."""

    def __init__(self, owner: AunTransport) -> None:
        self._owner = owner

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._owner._on_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        # An ICMP port-unreachable (e.g. transmitting to a station that is not
        # there) surfaces here. The pending transmit simply times out.
        pass


class AunTransport(EconetTransport):
    """Logical Econet over UDP/IP (AUN), as an EconetTransport.

    Station addresses are resolved to and from UDP endpoints by a peer map
    (:meth:`add_peer`). Outbound unicasts await an ``Ack``/``Nack`` correlated
    by handle, up to ``ack_timeout``; inbound unicasts are acknowledged on the
    application's behalf and delivered through async iteration.
    """

    _CAPABILITIES = frozenset(
        {
            TransportCapability.BROADCAST,
            TransportCapability.IMMEDIATE_REPLY,
            TransportCapability.MULTI_NET,
            TransportCapability.DISCOVERY,
        }
    )

    def __init__(
        self,
        name: str = "aun",
        *,
        local_station: Address,
        host: str = "0.0.0.0",
        port: int = DEFAULT_AUN_PORT,
        peers: dict[Address, tuple[str, int]] | None = None,
        ack_timeout: float = 2.0,
    ) -> None:
        super().__init__(name=name)
        self._local_station = local_station
        self._host = host
        self._port = port
        self._ack_timeout = ack_timeout
        self._peers: dict[Address, tuple[str, int]] = {}
        self._reverse: dict[tuple[str, int], Address] = {}
        for address, endpoint in (peers or {}).items():
            self.add_peer(address, *endpoint)
        self._udp: asyncio.DatagramTransport | None = None
        self._inbound: asyncio.Queue = asyncio.Queue()
        self._pending: dict[int, asyncio.Future[TransmitResult]] = {}
        self._handle = 0
        self._opened = False
        self._closed = False

    # -- introspection -------------------------------------------------

    @property
    def capabilities(self) -> frozenset[TransportCapability]:
        return self._CAPABILITIES

    @property
    def local_station(self) -> Address | None:
        return self._local_station

    @property
    def local_port(self) -> int:
        """The bound UDP port (valid after :meth:`open`)."""
        if self._udp is None:
            raise TransportConfigurationError("transport is not open")
        return self._udp.get_extra_info("sockname")[1]

    def add_peer(self, address: Address, host: str, port: int) -> None:
        """Map a station *address* to a UDP ``(host, port)`` endpoint."""
        self._peers[address] = (host, port)
        self._reverse[(host, port)] = address

    # -- lifecycle -----------------------------------------------------

    async def open(self) -> None:
        if self._opened:
            return
        loop = asyncio.get_running_loop()
        transport, _protocol = await loop.create_datagram_endpoint(
            lambda: _AunProtocol(self), local_addr=(self._host, self._port)
        )
        self._udp = transport
        self._opened = True

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._udp is not None:
            self._udp.close()
        self._inbound.put_nowait(_CLOSED)

    # -- outbound ------------------------------------------------------

    async def transmit(self, packet: EconetPacket) -> TransmitResult:
        return await self._send_awaiting_reply(packet)

    async def immediate(self, packet: EconetPacket) -> TransmitResult:
        return await self._send_awaiting_reply(packet)

    async def broadcast(self, payload: bytes, *, port: int, control: int) -> None:
        datagram = AunPacket(
            AunType.BROADCAST,
            port=port,
            control=control & 0x7F,
            handle=self._next_handle(),
            payload=payload,
        ).encode()
        for endpoint in self._peers.values():
            self._udp.sendto(datagram, endpoint)

    async def _send_awaiting_reply(self, packet: EconetPacket) -> TransmitResult:
        endpoint = self._peers.get(packet.dst)
        if endpoint is None:
            raise TransportConfigurationError(f"no AUN peer mapped for {packet.dst}")
        handle = self._next_handle()
        datagram = econet_to_aun(packet, handle=handle).encode()
        future: asyncio.Future[TransmitResult] = asyncio.get_running_loop().create_future()
        self._pending[handle] = future
        try:
            self._udp.sendto(datagram, endpoint)
            return await asyncio.wait_for(future, self._ack_timeout)
        except TimeoutError:
            return TransmitResult(TransmitOutcome.TIMEOUT)
        finally:
            self._pending.pop(handle, None)

    def _next_handle(self) -> int:
        self._handle = (self._handle + 4) % _HANDLE_MODULUS
        return self._handle

    # -- inbound -------------------------------------------------------

    def _on_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            datagram = AunPacket.decode(data)
        except EconetError:
            return  # drop malformed datagrams
        if datagram.type in (AunType.ACK, AunType.NACK, AunType.IMMEDIATE_REPLY):
            self._resolve_pending(datagram, addr)
            return
        source = self._reverse.get(addr)
        if source is None:
            return  # unattributable: no peer mapping for this endpoint
        self._inbound.put_nowait(
            aun_to_econet(datagram, dst=self._local_station, src=source)
        )
        if datagram.type is AunType.UNICAST:
            self._acknowledge(datagram, addr)

    def _acknowledge(self, datagram: AunPacket, addr: tuple[str, int]) -> None:
        ack = AunPacket(
            AunType.ACK, port=datagram.port, control=datagram.control, handle=datagram.handle
        )
        self._udp.sendto(ack.encode(), addr)

    def _resolve_pending(self, datagram: AunPacket, addr: tuple[str, int]) -> None:
        future = self._pending.get(datagram.handle)
        if future is None or future.done():
            return
        if datagram.type is AunType.ACK:
            future.set_result(TransmitResult(TransmitOutcome.ACKNOWLEDGED))
        elif datagram.type is AunType.NACK:
            future.set_result(TransmitResult(TransmitOutcome.NOT_LISTENING))
        else:  # IMMEDIATE_REPLY
            source = self._reverse.get(addr, self._local_station)
            reply = aun_to_econet(datagram, dst=self._local_station, src=source)
            future.set_result(TransmitResult(TransmitOutcome.ACKNOWLEDGED, reply=reply))

    def __aiter__(self) -> AsyncIterator[EconetPacket]:
        return self

    async def __anext__(self) -> EconetPacket:
        item = await self._inbound.get()
        if item is _CLOSED:
            raise StopAsyncIteration
        return item

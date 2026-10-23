"""The Station: an Econet service host that dispatches packets by port."""

from __future__ import annotations

import asyncio

from oaknut.econet.core import (
    Address,
    EconetPacket,
    PacketKind,
    TransmitResult,
)
from oaknut.econet.station.service import Service
from oaknut.extension import create_extension, namespace_for

_SERVICE_KIND = "econet.service"


class Station:
    """A logical Econet station hosting services over one transport.

    Register :class:`Service` instances directly with :meth:`register`, or load
    them as plug-ins by name with :meth:`register_extension`. :meth:`serve`
    consumes the transport's inbound packets and dispatches each, by port, to
    the service that claimed it — as an independent task. The transport's
    lifecycle is the caller's (``async with transport: await station.serve()``).
    """

    def __init__(self, transport, *, address: Address | None = None) -> None:
        self._transport = transport
        self._address = address if address is not None else transport.local_station
        self._services_by_port: dict[int, Service] = {}
        self._tasks: set[asyncio.Task] = set()

    @property
    def address(self) -> Address | None:
        return self._address

    @property
    def transport(self):
        return self._transport

    def register(self, service: Service) -> None:
        """Register *service*, claiming each of its ports (no port may clash)."""
        for port in service.ports:
            existing = self._services_by_port.get(port)
            if existing is not None:
                raise ValueError(f"port {port:#04x} is already claimed by {existing.name!r}")
            self._services_by_port[port] = service

    def register_extension(self, name: str, **kwargs) -> Service:
        """Load a service plug-in by name from the ``oaknut.econet.service`` axis
        and register it. Keyword arguments are passed to its constructor."""
        service = create_extension(_SERVICE_KIND, namespace_for(_SERVICE_KIND), name, **kwargs)
        self.register(service)
        return service

    @property
    def port_map(self) -> dict[int, str]:
        """Each claimed port mapped to the name of the service handling it."""
        return {port: service.name for port, service in self._services_by_port.items()}

    async def serve(self) -> None:
        """Dispatch inbound packets by port until the transport closes."""
        try:
            async for request in self._transport:
                service = self._services_by_port.get(request.port)
                if service is None:
                    continue
                task = asyncio.create_task(service.handle(request, self))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        finally:
            pending = list(self._tasks)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    async def reply(
        self,
        to: Address,
        *,
        port: int,
        control: int,
        payload: bytes = b"",
        kind: PacketKind = PacketKind.UNICAST,
    ) -> TransmitResult:
        """Send a reply from this station's address to a client's reply port."""
        if self._address is None:
            raise ValueError("station has no address to reply from")
        packet = EconetPacket(kind, to, self._address, control=control, port=port, payload=payload)
        return await self._transport.transmit(packet)

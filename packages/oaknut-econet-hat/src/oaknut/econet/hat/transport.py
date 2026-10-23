"""HatTransport — an EconetTransport driven over a KernelDevice."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from oaknut.econet.core import (
    BROADCAST_ADDRESS,
    Address,
    EconetError,
    EconetPacket,
    EconetTransport,
    PacketKind,
    TransmitResult,
    TransportCapability,
)
from oaknut.econet.hat.device import KernelDevice
from oaknut.econet.hat.mapping import (
    econet_to_kernel,
    empty_station_map,
    kernel_to_econet,
    set_station,
    tx_status_to_outcome,
)
from oaknut.econet.hat.wire import KernelPacket

_SEQ_MODULUS = 0x1_0000_0000


class _Closed:
    """Sentinel queued by close() to end inbound iteration."""


_CLOSED = _Closed()


class HatTransport(EconetTransport):
    """An EconetTransport over the econet-gpio kernel module, via a KernelDevice.

    The module runs the four-way handshake in its interrupt handler, so the host
    works in whole packets: a transmit writes the packet and the device returns
    the final TX status; inbound packets are decoded and delivered through async
    iteration. Transmits are serialised (the kernel handles one at a time).
    """

    _CAPABILITIES = frozenset(
        {
            TransportCapability.BROADCAST,
            TransportCapability.MONITOR,
            TransportCapability.MULTI_NET,
        }
    )

    @classmethod
    def from_config(cls, *, name: str, address: Address | None, config: dict) -> HatTransport:
        """Build from config: a ``device`` path becomes an
        :class:`EconetGpioDevice`."""
        from oaknut.econet.hat.gpio import EconetGpioDevice

        options = {key.replace("-", "_"): value for key, value in config.items()}
        device_options = {}
        if "device" in options:
            device_options["path"] = options.pop("device")
        for key in ("poll_interval", "tx_timeout"):
            if key in options:
                device_options[key] = options.pop(key)
        device = EconetGpioDevice(**device_options)
        return cls(name=name, device=device, local_station=address, **options)

    def __init__(
        self,
        name: str = "hat",
        *,
        device: KernelDevice,
        local_station: Address | None = None,
    ) -> None:
        super().__init__(name=name)
        self._device = device
        self._local_station = local_station
        self._inbound: asyncio.Queue = asyncio.Queue()
        self._tx_lock = asyncio.Lock()
        self._reader_task: asyncio.Task | None = None
        self._seq = 0
        self._opened = False
        self._closed = False

    @property
    def capabilities(self) -> frozenset[TransportCapability]:
        return self._CAPABILITIES

    @property
    def local_station(self) -> Address | None:
        return self._local_station

    async def open(self) -> None:
        if self._opened:
            return
        await self._device.open()
        if self._local_station is not None:
            bitmap = empty_station_map()
            set_station(bitmap, self._local_station)
            await self._device.set_stations(bytes(bitmap))
        self._reader_task = asyncio.create_task(self._read_loop())
        self._opened = True

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        await self._device.close()
        self._inbound.put_nowait(_CLOSED)

    async def transmit(self, packet: EconetPacket) -> TransmitResult:
        return TransmitResult(await self._send(econet_to_kernel(packet, seq=self._next_seq())))

    async def immediate(self, packet: EconetPacket) -> TransmitResult:
        return TransmitResult(await self._send(econet_to_kernel(packet, seq=self._next_seq())))

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
        await self._send(econet_to_kernel(packet, seq=self._next_seq()))

    async def _send(self, kernel_packet: KernelPacket):
        async with self._tx_lock:
            status = await self._device.transmit(kernel_packet.encode())
            return tx_status_to_outcome(status)

    def _next_seq(self) -> int:
        self._seq = (self._seq + 4) % _SEQ_MODULUS
        return self._seq

    async def _read_loop(self) -> None:
        async for raw in self._device:
            try:
                kernel = KernelPacket.decode(raw)
            except EconetError:
                continue  # ignore malformed packets; keep the device alive
            packet = kernel_to_econet(kernel)
            if packet is not None:
                self._inbound.put_nowait(packet)

    def __aiter__(self) -> AsyncIterator[EconetPacket]:
        return self

    async def __anext__(self) -> EconetPacket:
        item = await self._inbound.get()
        if item is _CLOSED:
            raise StopAsyncIteration
        return item

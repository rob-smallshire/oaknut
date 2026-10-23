"""PiconetTransport — an EconetTransport driven over a PicoLink."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

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
from oaknut.econet.piconet.link import PicoLink
from oaknut.econet.piconet.mapping import (
    broadcast_command_for,
    econet_to_tx_command,
    event_to_econet,
    tx_result_to_outcome,
)
from oaknut.econet.piconet.protocol import (
    PiconetMode,
    StatusEvent,
    TxResultEvent,
    parse_event,
    set_mode_command,
    set_station_command,
    status_command,
)

#: The Pico runs the four-way handshake itself, which (with ADLC timing) can
#: take a while; the host waits this long for the TX_RESULT before giving up.
DEFAULT_TX_TIMEOUT = 10.0


class _Closed:
    """Sentinel queued by close() to end inbound iteration."""


_CLOSED = _Closed()


class PiconetTransport(EconetTransport):
    """An EconetTransport over a Piconet board, reached through a PicoLink.

    The Pico firmware runs the four-way handshake, so the host works in whole
    packets. Commands are serialised: each TX/BCAST awaits its single
    ``TX_RESULT`` (there is no handle to correlate by). Inbound RX events are
    decoded to packets and delivered through async iteration.
    """

    _CAPABILITIES = frozenset(
        {TransportCapability.BROADCAST, TransportCapability.MONITOR}
    )

    @classmethod
    def from_config(cls, *, name: str, address: Address | None, config: dict) -> PiconetTransport:
        """Build from config: a serial ``port`` (and optional ``baudrate``)
        become a :class:`SerialPicoLink`."""
        from oaknut.econet.piconet.serial_link import SerialPicoLink

        options = {key.replace("-", "_"): value for key, value in config.items()}
        link_options = {}
        for key in ("port", "baudrate"):
            if key in options:
                link_options[key] = options.pop(key)
        link = SerialPicoLink(**link_options)
        return cls(name=name, link=link, local_station=address, **options)

    def __init__(
        self,
        name: str = "piconet",
        *,
        link: PicoLink,
        local_station: Address | None = None,
        tx_timeout: float = DEFAULT_TX_TIMEOUT,
    ) -> None:
        super().__init__(name=name)
        self._link = link
        self._local_station = local_station
        self._tx_timeout = tx_timeout
        self._inbound: asyncio.Queue = asyncio.Queue()
        self._tx_lock = asyncio.Lock()
        self._pending_tx: asyncio.Future[TxResultEvent] | None = None
        self._pending_status: asyncio.Future[StatusEvent] | None = None
        self._reader_task: asyncio.Task | None = None
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
        await self._link.open()
        self._reader_task = asyncio.create_task(self._read_loop())
        if self._local_station is not None:
            await self._link.send_line(set_station_command(self._local_station.station))
        await self._link.send_line(set_mode_command(PiconetMode.LISTEN))
        self._opened = True

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        await self._link.close()
        self._inbound.put_nowait(_CLOSED)

    async def transmit(self, packet: EconetPacket) -> TransmitResult:
        return TransmitResult(await self._send_awaiting_result(econet_to_tx_command(packet)))

    async def immediate(self, packet: EconetPacket) -> TransmitResult:
        # Piconet has no host-driven immediate-reply path, so this best-effort
        # sends the operation and reports its delivery outcome with no reply.
        return TransmitResult(await self._send_awaiting_result(econet_to_tx_command(packet)))

    async def broadcast(self, payload: bytes, *, port: int, control: int) -> None:
        await self._send_awaiting_result(
            broadcast_command_for(payload, port=port, control=control)
        )

    async def status(self) -> StatusEvent:
        """Query the board: firmware version, station, SR1 (clock state), mode."""
        self._pending_status = asyncio.get_running_loop().create_future()
        try:
            await self._link.send_line(status_command())
            return await asyncio.wait_for(self._pending_status, self._tx_timeout)
        except TimeoutError as exc:
            raise TransportConfigurationError("no STATUS response from the Piconet board") from exc
        finally:
            self._pending_status = None

    async def _send_awaiting_result(self, command: str) -> TransmitOutcome:
        async with self._tx_lock:
            self._pending_tx = asyncio.get_running_loop().create_future()
            try:
                await self._link.send_line(command)
                event = await asyncio.wait_for(self._pending_tx, self._tx_timeout)
                return tx_result_to_outcome(event.result)
            except TimeoutError:
                return TransmitOutcome.TIMEOUT
            finally:
                self._pending_tx = None

    async def _read_loop(self) -> None:
        async for line in self._link:
            try:
                event = parse_event(line)
            except EconetError:
                continue  # ignore malformed lines; keep the link alive
            if isinstance(event, StatusEvent):
                if self._pending_status is not None and not self._pending_status.done():
                    self._pending_status.set_result(event)
                continue
            if isinstance(event, TxResultEvent):
                if self._pending_tx is not None and not self._pending_tx.done():
                    self._pending_tx.set_result(event)
                continue
            packet = event_to_econet(event)
            if packet is not None:
                self._inbound.put_nowait(packet)

    def __aiter__(self) -> AsyncIterator[EconetPacket]:
        return self

    async def __anext__(self) -> EconetPacket:
        item = await self._inbound.get()
        if item is _CLOSED:
            raise StopAsyncIteration
        return item

"""SerialPicoLink: a PicoLink over a USB serial port (pyserial-asyncio).

pyserial-asyncio is an optional dependency (the ``serial`` extra) and is
imported lazily, so this module — and the package — import fine without it;
only opening a real serial link requires it. The pure helpers (line framing,
port matching) are testable without any serial hardware or library.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable

from oaknut.econet.core import TransportConfigurationError
from oaknut.econet.piconet.link import PicoLink

#: USB identifiers and line rate of a Piconet board.
PICO_VID = 0x2E8A
PICO_PID = 0x000A
PICO_BAUD = 115200


class _LineBuffer:
    """Accumulates received bytes and yields complete CR/LF-delimited lines."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[str]:
        self._buffer.extend(data)
        lines: list[str] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            raw = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            line = raw.decode("ascii", errors="replace").rstrip("\r")
            if line:
                lines.append(line)
        return lines


def match_pico_port(ports: Iterable) -> str | None:
    """Return the device path of the first Pico (by USB VID/PID), or None."""
    for port in ports:
        if getattr(port, "vid", None) == PICO_VID and getattr(port, "pid", None) == PICO_PID:
            return port.device
    return None


def _find_pico_port() -> str | None:
    from serial.tools import list_ports  # lazy: part of pyserial

    return match_pico_port(list_ports.comports())


class _Closed:
    """Sentinel queued to end inbound iteration."""


_CLOSED = _Closed()


class _SerialProtocol(asyncio.Protocol):
    def __init__(self, owner: SerialPicoLink) -> None:
        self._owner = owner

    def data_received(self, data: bytes) -> None:
        self._owner._feed(data)

    def connection_lost(self, exc: Exception | None) -> None:
        self._owner._on_connection_lost()


class SerialPicoLink(PicoLink):
    """A PicoLink over a USB-CDC serial port to a real Piconet board.

    With no explicit ``port`` the device is auto-detected by USB VID/PID. The
    ``serial`` extra (pyserial-asyncio) must be installed to open the link.
    """

    def __init__(self, *, port: str | None = None, baudrate: int = PICO_BAUD) -> None:
        self._port = port
        self._baudrate = baudrate
        self._transport: asyncio.Transport | None = None
        self._inbound: asyncio.Queue = asyncio.Queue()
        self._lines = _LineBuffer()
        self._closed = False

    async def open(self) -> None:
        try:
            import serial_asyncio
        except ModuleNotFoundError as exc:
            raise TransportConfigurationError(
                "pyserial-asyncio is required for the serial Piconet link; "
                "install oaknut-econet-piconet[serial]"
            ) from exc
        port = self._port or _find_pico_port()
        if port is None:
            raise TransportConfigurationError(
                "no Piconet device found by USB id; pass port= explicitly"
            )
        loop = asyncio.get_running_loop()
        self._transport, _ = await serial_asyncio.create_serial_connection(
            loop, lambda: _SerialProtocol(self), url=port, baudrate=self._baudrate
        )

    async def send_line(self, line: str) -> None:
        if self._transport is None:
            raise TransportConfigurationError("serial link is not open")
        self._transport.write((line + "\r\n").encode("ascii"))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._transport is not None:
            self._transport.close()
        self._inbound.put_nowait(_CLOSED)

    def _feed(self, data: bytes) -> None:
        for line in self._lines.feed(data):
            self._inbound.put_nowait(line)

    def _on_connection_lost(self) -> None:
        self._inbound.put_nowait(_CLOSED)

    def __aiter__(self) -> AsyncIterator[str]:
        return self

    async def __anext__(self) -> str:
        item = await self._inbound.get()
        if item is _CLOSED:
            raise StopAsyncIteration
        return item

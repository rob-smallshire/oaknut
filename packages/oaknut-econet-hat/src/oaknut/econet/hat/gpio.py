"""EconetGpioDevice — the real /dev/econet-gpio client (Linux + HAT only).

Uses only the standard library. ``fcntl`` is imported lazily inside the methods
so this module imports on any platform (the FakeKernelDevice path, and the
ioctl-number computation, work everywhere); only opening the real device needs
a Linux kernel with the econet-gpio module loaded.

ioctl request numbers are computed with the Linux asm-generic encoding (what
the Raspberry Pi kernel uses), independent of the host platform's headers.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import struct
from collections.abc import AsyncIterator

from oaknut.econet.core import TransportConfigurationError
from oaknut.econet.hat.device import KernelDevice
from oaknut.econet.hat.mapping import is_in_progress
from oaknut.econet.hat.wire import TxStatus

DEFAULT_DEVICE_PATH = "/dev/econet-gpio"
_MAX_PACKET_SIZE = 32768

# Linux asm-generic ioctl encoding (NR=8, TYPE=8, SIZE=14, DIR=2 bits).
_NRSHIFT = 0
_TYPESHIFT = 8
_SIZESHIFT = 16
_DIRSHIFT = 30
_DIR_NONE, _DIR_WRITE, _DIR_READ = 0, 1, 2
_MAGIC = 0xA9
_INT_SIZE = struct.calcsize("i")
_PTR_SIZE = struct.calcsize("P")


def _ioc(direction: int, nr: int, size: int) -> int:
    return (
        (direction << _DIRSHIFT)
        | (size << _SIZESHIFT)
        | (_MAGIC << _TYPESHIFT)
        | (nr << _NRSHIFT)
    )


IOC_RESET = _ioc(_DIR_NONE, 0, 0)
IOC_SET_STATIONS = _ioc(_DIR_WRITE, 5, _PTR_SIZE)
IOC_AUNMODE = _ioc(_DIR_WRITE, 6, _INT_SIZE)
IOC_TXERR = _ioc(_DIR_READ, 8, _INT_SIZE)
IOC_READMODE = _ioc(_DIR_NONE, 9, 0)


class _Closed:
    """Sentinel queued by close() to end inbound iteration."""


_CLOSED = _Closed()


class EconetGpioDevice(KernelDevice):
    """A KernelDevice backed by the real ``/dev/econet-gpio`` character device.

    On :meth:`open` it resets the module, enables AUN (four-way) mode, and
    watches the fd for inbound packets. :meth:`transmit` writes a packet then
    polls the TXERR ioctl — yielding to the event loop between polls rather than
    busy-waiting — until a terminal status, which it returns.
    """

    def __init__(
        self,
        *,
        path: str = DEFAULT_DEVICE_PATH,
        poll_interval: float = 0.001,
        tx_timeout: float = 10.0,
    ) -> None:
        self._path = path
        self._poll_interval = poll_interval
        self._tx_timeout = tx_timeout
        self._fd: int | None = None
        self._inbound: asyncio.Queue = asyncio.Queue()
        self._closed = False

    async def open(self) -> None:
        import fcntl

        try:
            self._fd = os.open(self._path, os.O_RDWR | os.O_NONBLOCK)
        except OSError as exc:
            raise TransportConfigurationError(f"cannot open {self._path}: {exc}") from exc
        fcntl.ioctl(self._fd, IOC_RESET)
        fcntl.ioctl(self._fd, IOC_AUNMODE, struct.pack("i", 1))
        asyncio.get_running_loop().add_reader(self._fd, self._on_readable)

    async def set_stations(self, bitmap: bytes) -> None:
        import fcntl

        if self._fd is None:
            raise TransportConfigurationError("device is not open")
        fcntl.ioctl(self._fd, IOC_SET_STATIONS, bytes(bitmap))

    async def transmit(self, packet: bytes) -> int:
        import fcntl

        if self._fd is None:
            raise TransportConfigurationError("device is not open")
        try:
            os.write(self._fd, packet)
        except BlockingIOError:
            return int(TxStatus.BUSY)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._tx_timeout
        while True:
            result = fcntl.ioctl(self._fd, IOC_TXERR, struct.pack("i", 0))
            status = struct.unpack("i", result)[0] & 0xFF
            if not is_in_progress(status):
                return status
            if loop.time() >= deadline:
                return status
            await asyncio.sleep(self._poll_interval)

    def _on_readable(self) -> None:
        try:
            data = os.read(self._fd, _MAX_PACKET_SIZE)
        except (BlockingIOError, OSError):
            return
        if data:
            self._inbound.put_nowait(data)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._fd is not None:
            with contextlib.suppress(Exception):
                asyncio.get_running_loop().remove_reader(self._fd)
            with contextlib.suppress(OSError):
                os.close(self._fd)
        self._inbound.put_nowait(_CLOSED)

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        item = await self._inbound.get()
        if item is _CLOSED:
            raise StopAsyncIteration
        return item

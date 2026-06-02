"""Piconet transport for oaknut-econet: a Pico serial-to-Econet adapter.

The Pico firmware runs the Econet four-way handshake and speaks a line-based
serial protocol (base64 payloads). This package provides the protocol codec,
the Econet frame parsing, the mapping to/from
:class:`~oaknut.econet.core.EconetPacket`, :class:`PiconetTransport` (driven
over a :class:`PicoLink`), and :class:`FakePiconet` — an in-process firmware
simulation so the transport is testable in CI with no hardware.

It registers on the ``oaknut.econet.transport`` extension axis as ``piconet``.
"""

from __future__ import annotations

from oaknut.econet.piconet.fake import FakePiconet
from oaknut.econet.piconet.link import PicoLink
from oaknut.econet.piconet.protocol import PiconetMode, TxResult
from oaknut.econet.piconet.serial_link import SerialPicoLink
from oaknut.econet.piconet.transport import PiconetTransport

__version__ = "12.5.3"

__all__ = [
    "FakePiconet",
    "PicoLink",
    "PiconetMode",
    "PiconetTransport",
    "SerialPicoLink",
    "TxResult",
]

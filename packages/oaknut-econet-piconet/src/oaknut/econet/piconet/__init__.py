"""Piconet transport for oaknut-econet: a Pico serial-to-Econet adapter.

The Pico firmware runs the Econet four-way handshake and speaks a line-based
serial protocol (base64 payloads). This package provides the protocol codec,
the Econet frame parsing, the mapping to/from
:class:`~oaknut.econet.core.EconetPacket`, :class:`PiconetTransport` (driven
over a :class:`PicoLink`), and :class:`FakePiconet` — an in-process firmware
simulation so the transport is testable in CI with no hardware.

It registers on the ``oaknut.econet.transport`` extension axis as ``piconet``.
"""

__version__ = "12.5.3"

__all__: list[str] = []

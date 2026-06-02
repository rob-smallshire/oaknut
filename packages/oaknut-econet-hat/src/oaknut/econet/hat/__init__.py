"""PiEconetHAT transport for oaknut-econet: a client of the econet-gpio module.

The kernel module runs the Econet four-way handshake and exposes
``/dev/econet-gpio``, through which user space exchanges AUN-format packets
(``struct __econet_packet_aun``) and issues ioctls. This package provides the
packet-struct codec, the mapping to/from
:class:`~oaknut.econet.core.EconetPacket`, :class:`HatTransport` (driven over a
:class:`KernelDevice`), and :class:`FakeKernelDevice` — an in-process
simulation so the transport is testable in CI with no hardware.

It registers on the ``oaknut.econet.transport`` extension axis as ``hat``.
"""

__version__ = "12.5.3"

__all__: list[str] = []

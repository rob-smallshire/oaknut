"""AUN transport for oaknut-econet: logical Econet over UDP/IP.

AUN (Acorn Universal Networking) carries Econet traffic over UDP datagrams,
collapsing the four-way handshake into a two-packet (Unicast + Ack) exchange.
This package provides:

- the AUN wire codec (:class:`AunPacket` / :class:`AunType`),
- the mapping between :class:`~oaknut.econet.core.EconetPacket` and AUN packets,
- :class:`AunTransport`, an :class:`~oaknut.econet.core.EconetTransport` over an
  ``asyncio`` UDP endpoint, and
- optional mDNS station advertisement/discovery (the ``_aun._udp`` convention),
  available with the ``mdns`` extra.

It registers on the ``oaknut.econet.transport`` extension axis as ``aun``.
"""

__version__ = "12.5.3"

__all__: list[str] = []

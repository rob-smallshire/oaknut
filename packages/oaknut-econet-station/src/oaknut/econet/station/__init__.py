"""The Econet service host: a Station that dispatches packets to Services.

A :class:`Station` owns an :class:`~oaknut.econet.core.EconetTransport`, runs
its inbound loop, and dispatches each received packet by port to the registered
:class:`Service` for it — each handled as an independent ``asyncio`` task. A
service replies by transmitting back to the client's nominated reply port.

This is the application-layer foundation: a file server, print server, DSCP
server, or key-value store is each just a :class:`Service` on a :class:`Station`.
See ``docs/dev/econet-design.md`` §13.
"""

from __future__ import annotations

from oaknut.econet.station.host import Station
from oaknut.econet.station.service import Service

__version__ = "12.5.3"

__all__ = [
    "Service",
    "Station",
]

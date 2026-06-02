"""The Service extension: a plug-in handler for one Econet protocol.

A :class:`Service` is an oaknut :class:`~oaknut.extension.Extension` on the
``oaknut.econet.service`` axis, so a station host can discover and load services
as plug-ins (entry-point group ``oaknut.econet.service``) and configure a
deployment declaratively. Each service declares the ports it claims; the
:class:`~oaknut.econet.station.Station` registers it for those ports and
dispatches matching inbound packets to it.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from oaknut.econet.core import EconetPacket
from oaknut.extension import Extension

if TYPE_CHECKING:
    from oaknut.econet.station.host import Station


class Service(Extension):
    """A handler for one Econet protocol, bound to the ports it claims.

    Concrete services subclass this, return their ports from :attr:`ports`,
    implement :meth:`handle`, and register an entry point under
    ``oaknut.econet.service`` to be loadable as a plug-in.
    """

    @classmethod
    def _kind(cls) -> str:
        return "econet.service"

    @classmethod
    def from_config(cls, *, name: str, config: dict) -> Service:
        """Build a service from a host config table.

        The default treats *config* as flat constructor keyword arguments (with
        hyphenated keys mapped to underscores). Services with structured config
        override this.
        """
        kwargs = {key.replace("-", "_"): value for key, value in config.items()}
        return cls(name=name, **kwargs)

    @property
    @abstractmethod
    def ports(self) -> frozenset[int]:
        """The ports this service claims on its station."""

    @abstractmethod
    async def handle(self, request: EconetPacket, station: Station) -> None:
        """Handle one inbound request, replying via ``station.reply(...)``."""

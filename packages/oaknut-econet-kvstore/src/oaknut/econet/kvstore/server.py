"""KvServer — a dict-backed key-value Service plug-in."""

from __future__ import annotations

from typing import TYPE_CHECKING

from oaknut.econet.core import EconetError, EconetPacket
from oaknut.econet.kvstore.protocol import (
    KV_CONTROL,
    KV_REQUEST_PORT,
    KvOp,
    KvReply,
    KvRequest,
    KvStatus,
    decode_request,
    encode_reply,
)
from oaknut.econet.station import Service

if TYPE_CHECKING:
    from oaknut.econet.station import Station


class KvServer(Service):
    """A key-value store served over Econet, backed by a plain dict.

    Registered as the ``kvstore`` plug-in on the ``oaknut.econet.service`` axis;
    claims :data:`KV_REQUEST_PORT`. Replies to each request on the reply port
    the client nominated.
    """

    def __init__(self, name: str = "kvstore", *, store: dict[bytes, bytes] | None = None) -> None:
        super().__init__(name=name)
        self._store: dict[bytes, bytes] = {} if store is None else store

    @property
    def ports(self) -> frozenset[int]:
        return frozenset({KV_REQUEST_PORT})

    async def handle(self, request: EconetPacket, station: Station) -> None:
        try:
            kv_request = decode_request(request.payload)
        except EconetError:
            return  # ignore malformed requests
        reply = self._apply(kv_request)
        await station.reply(
            request.src,
            port=kv_request.reply_port,
            control=KV_CONTROL,
            payload=encode_reply(status=reply.status, value=reply.value),
        )

    def _apply(self, request: KvRequest) -> KvReply:
        if request.op is KvOp.GET:
            value = self._store.get(request.key)
            if value is None:
                return KvReply(KvStatus.NOT_FOUND)
            return KvReply(KvStatus.OK, value)
        if request.op is KvOp.PUT:
            self._store[request.key] = request.value
            return KvReply(KvStatus.OK)
        if request.op is KvOp.DELETE:
            if self._store.pop(request.key, None) is None:
                return KvReply(KvStatus.NOT_FOUND)
            return KvReply(KvStatus.OK)
        return KvReply(KvStatus.ERROR)

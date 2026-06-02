"""KvClient — the matching client for the Econet key-value store."""

from __future__ import annotations

from oaknut.econet.core import (
    Address,
    EconetError,
    EconetPacket,
    EconetTransport,
    PacketKind,
)
from oaknut.econet.kvstore.protocol import (
    KV_CONTROL,
    KV_REPLY_PORT,
    KV_REQUEST_PORT,
    KvOp,
    KvReply,
    KvStatus,
    decode_reply,
    encode_request,
)


class KvClient:
    """A single-flight client for a :class:`KvServer`.

    Each call transmits a request to the server and awaits the reply on the
    nominated reply port. Drive one request at a time (it consumes the
    transport's inbound stream until its reply arrives).
    """

    def __init__(
        self,
        transport: EconetTransport,
        *,
        server: Address,
        reply_port: int = KV_REPLY_PORT,
    ) -> None:
        self._transport = transport
        self._server = server
        self._reply_port = reply_port

    async def get(self, key: bytes) -> bytes | None:
        reply = await self._request(KvOp.GET, key)
        return reply.value if reply.status is KvStatus.OK else None

    async def put(self, key: bytes, value: bytes) -> None:
        await self._request(KvOp.PUT, key, value)

    async def delete(self, key: bytes) -> bool:
        reply = await self._request(KvOp.DELETE, key)
        return reply.status is KvStatus.OK

    async def _request(self, op: KvOp, key: bytes, value: bytes = b"") -> KvReply:
        payload = encode_request(reply_port=self._reply_port, op=op, key=key, value=value)
        request = EconetPacket(
            PacketKind.UNICAST,
            self._server,
            self._transport.local_station,
            control=KV_CONTROL,
            port=KV_REQUEST_PORT,
            payload=payload,
        )
        await self._transport.transmit(request)
        async for packet in self._transport:
            if packet.port == self._reply_port:
                return decode_reply(packet.payload)
        raise EconetError("transport closed before a KV reply arrived")

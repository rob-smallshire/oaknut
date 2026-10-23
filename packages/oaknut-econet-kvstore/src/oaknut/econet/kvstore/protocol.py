"""The (deliberately tiny) Econet key-value protocol.

A request, sent on :data:`KV_REQUEST_PORT`, is::

    [reply_port][op][key_len][key ...][value ...]

A reply, sent back to the request's reply port, is::

    [status][value ...]

Keys are limited to 255 bytes (a single length byte). This is a worked example,
not a serious store — it exists to exercise the service-host stack end to end.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from oaknut.econet.core import EconetError

#: Port the server listens on for requests.
KV_REQUEST_PORT = 0xB0
#: Port a client listens on for replies (carried in each request).
KV_REPLY_PORT = 0xB1
#: Control byte used for KV traffic.
KV_CONTROL = 0x80


class KvOp(IntEnum):
    GET = 1
    PUT = 2
    DELETE = 3


class KvStatus(IntEnum):
    OK = 0
    NOT_FOUND = 1
    ERROR = 2


@dataclass(frozen=True, slots=True)
class KvRequest:
    reply_port: int
    op: KvOp
    key: bytes
    value: bytes = b""


@dataclass(frozen=True, slots=True)
class KvReply:
    status: KvStatus
    value: bytes = b""


def encode_request(*, reply_port: int, op: KvOp, key: bytes, value: bytes = b"") -> bytes:
    if len(key) > 255:
        raise ValueError(f"key too long: {len(key)} bytes (max 255)")
    return bytes([reply_port, int(op), len(key)]) + key + value


def decode_request(payload: bytes) -> KvRequest:
    if len(payload) < 3:
        raise EconetError(f"KV request too short: {len(payload)} bytes")
    reply_port, op_byte, key_len = payload[0], payload[1], payload[2]
    if len(payload) < 3 + key_len:
        raise EconetError("KV request key length exceeds the payload")
    try:
        op = KvOp(op_byte)
    except ValueError as exc:
        raise EconetError(f"unknown KV op {op_byte:#04x}") from exc
    return KvRequest(
        reply_port=reply_port,
        op=op,
        key=bytes(payload[3 : 3 + key_len]),
        value=bytes(payload[3 + key_len :]),
    )


def encode_reply(*, status: KvStatus, value: bytes = b"") -> bytes:
    return bytes([int(status)]) + value


def decode_reply(payload: bytes) -> KvReply:
    if len(payload) < 1:
        raise EconetError("KV reply too short")
    try:
        status = KvStatus(payload[0])
    except ValueError as exc:
        raise EconetError(f"unknown KV status {payload[0]:#04x}") from exc
    return KvReply(status=status, value=bytes(payload[1:]))

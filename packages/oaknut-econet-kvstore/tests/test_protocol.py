"""Contract for the tiny KV request/reply codec."""

import pytest
from oaknut.econet.core import EconetError
from oaknut.econet.kvstore.protocol import (
    KV_REPLY_PORT,
    KV_REQUEST_PORT,
    KvOp,
    KvReply,
    KvRequest,
    KvStatus,
    decode_reply,
    decode_request,
    encode_reply,
    encode_request,
)


def test_ports_ops_and_statuses():
    assert KV_REQUEST_PORT == 0xB0
    assert KV_REPLY_PORT == 0xB1
    assert (KvOp.GET, KvOp.PUT, KvOp.DELETE) == (1, 2, 3)
    assert (KvStatus.OK, KvStatus.NOT_FOUND, KvStatus.ERROR) == (0, 1, 2)


def test_encode_request_known_vector():
    assert encode_request(reply_port=0xB1, op=KvOp.PUT, key=b"k", value=b"v") == b"\xb1\x02\x01kv"


def test_request_round_trips():
    request = decode_request(encode_request(reply_port=0xB1, op=KvOp.GET, key=b"colour"))
    assert request == KvRequest(reply_port=0xB1, op=KvOp.GET, key=b"colour", value=b"")


def test_request_round_trips_with_a_value():
    request = decode_request(
        encode_request(reply_port=0xB1, op=KvOp.PUT, key=b"k", value=b"hello")
    )
    assert request == KvRequest(0xB1, KvOp.PUT, b"k", b"hello")


def test_reply_round_trips():
    assert decode_reply(encode_reply(status=KvStatus.OK, value=b"blue")) == KvReply(
        KvStatus.OK, b"blue"
    )
    assert decode_reply(encode_reply(status=KvStatus.NOT_FOUND)) == KvReply(KvStatus.NOT_FOUND, b"")


def test_decode_request_rejects_short_buffer():
    with pytest.raises(EconetError):
        decode_request(b"\xb1\x02")


def test_decode_request_rejects_a_bad_key_length():
    with pytest.raises(EconetError):
        decode_request(bytes([0xB1, 2, 10]) + b"abc")  # claims a 10-byte key, only 3 present


def test_decode_request_rejects_an_unknown_op():
    with pytest.raises(EconetError):
        decode_request(bytes([0xB1, 9, 0]))


def test_encode_request_rejects_an_overlong_key():
    with pytest.raises(ValueError):
        encode_request(reply_port=0xB1, op=KvOp.GET, key=b"x" * 256)


def test_decode_reply_rejects_an_empty_buffer():
    with pytest.raises(EconetError):
        decode_reply(b"")

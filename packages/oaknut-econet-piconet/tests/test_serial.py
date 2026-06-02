"""Hermetic tests for the serial link's pure helpers (no hardware, no pyserial)."""

from collections import namedtuple

from oaknut.econet.piconet.serial_link import _LineBuffer, match_pico_port

_Port = namedtuple("_Port", "device vid pid")


def test_line_buffer_splits_on_crlf():
    assert _LineBuffer().feed(b"STATUS 2.0.20 1 0xff 1\r\n") == ["STATUS 2.0.20 1 0xff 1"]


def test_line_buffer_accumulates_partial_lines():
    buffer = _LineBuffer()
    assert buffer.feed(b"TX_RES") == []
    assert buffer.feed(b"ULT OK\r\n") == ["TX_RESULT OK"]


def test_line_buffer_yields_multiple_lines():
    assert _LineBuffer().feed(b"A\r\nB\r\nC\r\n") == ["A", "B", "C"]


def test_line_buffer_tolerates_bare_lf_and_skips_blanks():
    assert _LineBuffer().feed(b"\nX\n\nY\n") == ["X", "Y"]


def test_match_pico_port_finds_the_pico_by_usb_id():
    ports = [_Port("/dev/ttyX", 0x1234, 0x5678), _Port("/dev/ttyACM0", 0x2E8A, 0x000A)]
    assert match_pico_port(ports) == "/dev/ttyACM0"


def test_match_pico_port_returns_none_when_absent():
    assert match_pico_port([_Port("/dev/ttyX", 0x1234, 0x5678)]) is None

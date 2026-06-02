"""Contract for the Piconet serial line protocol codec."""

import base64

import pytest
from oaknut.econet.core import EconetError
from oaknut.econet.piconet.protocol import (
    ErrorEvent,
    MonitorEvent,
    PiconetMode,
    RxBroadcastEvent,
    RxImmediateEvent,
    RxTransmitEvent,
    StatusEvent,
    TxResult,
    TxResultEvent,
    bcast_command,
    parse_event,
    restart_command,
    set_mode_command,
    set_station_command,
    status_command,
    tx_command,
)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# -- command formatting (host -> Pico) -------------------------------


def test_simple_commands():
    assert status_command() == "STATUS"
    assert restart_command() == "RESTART"


def test_set_mode_uses_decimal_mode():
    assert set_mode_command(PiconetMode.STOP) == "SET_MODE 0"
    assert set_mode_command(PiconetMode.LISTEN) == "SET_MODE 1"
    assert set_mode_command(PiconetMode.MONITOR) == "SET_MODE 2"


def test_set_station():
    assert set_station_command(171) == "SET_STATION 171"


def test_tx_command_uses_decimal_fields_and_base64_data():
    line = tx_command(station=254, network=0, control=0x80, port=0x99, data=b"Hi")
    assert line == f"TX 254 0 128 153 {_b64(b'Hi')}"


def test_tx_command_appends_base64_scout_extra_when_present():
    line = tx_command(
        station=254, network=0, control=0x80, port=0x99, data=b"Hi", scout_extra=b"\x01\x02"
    )
    assert line == f"TX 254 0 128 153 {_b64(b'Hi')} {_b64(b'\x01\x02')}"


def test_bcast_command():
    assert bcast_command(b"\x01\x02") == f"BCAST {_b64(b'\x01\x02')}"


# -- event parsing (Pico -> host) ------------------------------------


def test_parse_status_event():
    event = parse_event("STATUS 2.0.20 171 0xff 1")
    assert isinstance(event, StatusEvent)
    assert event.version == "2.0.20"
    assert event.station == 171
    assert event.sr1 == 0xFF
    assert event.mode is PiconetMode.LISTEN


def test_parse_tx_result_ok():
    event = parse_event("TX_RESULT OK")
    assert isinstance(event, TxResultEvent)
    assert event.result is TxResult.OK


def test_parse_tx_result_failure():
    assert parse_event("TX_RESULT NO_SCOUT_ACK").result is TxResult.NO_SCOUT_ACK


def test_parse_rx_broadcast():
    frame = b"\xff\xff\x02\x00\x80\x99hello"
    event = parse_event(f"RX_BROADCAST {_b64(frame)}")
    assert isinstance(event, RxBroadcastEvent)
    assert event.frame == frame


def test_parse_rx_transmit_has_reply_id_scout_and_data():
    scout = b"\x01\x00\x02\x00\x80\x99"
    data = b"\x01\x00\x02\x00payload"
    event = parse_event(f"RX_TRANSMIT 5 {_b64(scout)} {_b64(data)}")
    assert isinstance(event, RxTransmitEvent)
    assert event.reply_id == 5
    assert event.scout == scout
    assert event.data == data


def test_parse_rx_immediate_has_scout_and_data():
    scout = b"\x01\x00\x02\x00\x88\x00"
    data = b"\x01\x00\x02\x00"
    event = parse_event(f"RX_IMMEDIATE {_b64(scout)} {_b64(data)}")
    assert isinstance(event, RxImmediateEvent)
    assert event.scout == scout
    assert event.data == data


def test_parse_monitor():
    frame = b"\x01\x00\x02\x00\x80\x99data"
    event = parse_event(f"MONITOR {_b64(frame)}")
    assert isinstance(event, MonitorEvent)
    assert event.frame == frame


def test_parse_error_keeps_the_whole_description():
    event = parse_event("ERROR something went wrong")
    assert isinstance(event, ErrorEvent)
    assert event.description == "something went wrong"


def test_parse_unknown_event_raises():
    with pytest.raises(EconetError):
        parse_event("WAT foo bar")

"""The Piconet serial line protocol: command formatting and event parsing.

One command or event per line. Commands go host -> Pico; events come back
Pico -> host. Binary payloads are base64-encoded. The functions here produce
and parse the bare line content; the link layer adds the line terminator.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from enum import Enum, IntEnum

from oaknut.econet.core import EconetError


class PiconetMode(IntEnum):
    """The board operating mode (the SET_MODE argument)."""

    STOP = 0
    LISTEN = 1
    MONITOR = 2


class TxResult(str, Enum):
    """The outcome reported by a TX_RESULT event."""

    OK = "OK"
    UNINITIALISED = "UNINITIALISED"
    OVERFLOW = "OVERFLOW"
    UNDERRUN = "UNDERRUN"
    LINE_JAMMED = "LINE_JAMMED"
    NO_SCOUT_ACK = "NO_SCOUT_ACK"
    NO_DATA_ACK = "NO_DATA_ACK"
    TIMEOUT = "TIMEOUT"
    INVALID_RECEIVE_ID = "INVALID_RECEIVE_ID"
    MISC = "MISC"
    UNEXPECTED = "UNEXPECTED"


# -- commands (host -> Pico) -----------------------------------------


def status_command() -> str:
    return "STATUS"


def restart_command() -> str:
    return "RESTART"


def set_mode_command(mode: PiconetMode) -> str:
    return f"SET_MODE {int(mode)}"


def set_station_command(station: int) -> str:
    return f"SET_STATION {station}"


def tx_command(
    *,
    station: int,
    network: int,
    control: int,
    port: int,
    data: bytes,
    scout_extra: bytes | None = None,
) -> str:
    """Format a TX command (all fields decimal except the base64 payloads)."""
    line = f"TX {station} {network} {control} {port} {_b64encode(data)}"
    if scout_extra is not None:
        line += f" {_b64encode(scout_extra)}"
    return line


def bcast_command(data: bytes) -> str:
    return f"BCAST {_b64encode(data)}"


# -- events (Pico -> host) -------------------------------------------


class PiconetEvent:
    """Base class for parsed Pico -> host events."""

    __slots__ = ()


@dataclass(frozen=True)
class StatusEvent(PiconetEvent):
    version: str
    station: int
    sr1: int
    mode: PiconetMode


@dataclass(frozen=True)
class TxResultEvent(PiconetEvent):
    result: TxResult


@dataclass(frozen=True)
class RxBroadcastEvent(PiconetEvent):
    frame: bytes


@dataclass(frozen=True)
class RxTransmitEvent(PiconetEvent):
    reply_id: int
    scout: bytes
    data: bytes


@dataclass(frozen=True)
class RxImmediateEvent(PiconetEvent):
    scout: bytes
    data: bytes


@dataclass(frozen=True)
class MonitorEvent(PiconetEvent):
    frame: bytes


@dataclass(frozen=True)
class ErrorEvent(PiconetEvent):
    description: str


def parse_event(line: str) -> PiconetEvent:
    """Parse one Pico -> host event line, raising EconetError if malformed."""
    line = line.strip()
    if not line:
        raise EconetError("empty Piconet event line")
    keyword, _, rest = line.partition(" ")
    parser = _EVENT_PARSERS.get(keyword)
    if parser is None:
        raise EconetError(f"unknown Piconet event {keyword!r}")
    return parser(rest.strip())


def _parse_status(rest: str) -> StatusEvent:
    parts = rest.split()
    if len(parts) != 4:
        raise EconetError(f"malformed STATUS event: {rest!r}")
    version, station, sr1, mode = parts
    try:
        return StatusEvent(
            version=version,
            station=int(station),
            sr1=int(sr1, 0),
            mode=PiconetMode(int(mode)),
        )
    except ValueError as exc:
        raise EconetError(f"malformed STATUS event: {exc}") from exc


def _parse_tx_result(rest: str) -> TxResultEvent:
    try:
        return TxResultEvent(TxResult(rest))
    except ValueError as exc:
        raise EconetError(f"unknown TX_RESULT {rest!r}") from exc


def _parse_rx_broadcast(rest: str) -> RxBroadcastEvent:
    return RxBroadcastEvent(frame=_b64decode(rest))


def _parse_rx_transmit(rest: str) -> RxTransmitEvent:
    parts = rest.split()
    if len(parts) != 3:
        raise EconetError(f"malformed RX_TRANSMIT event: {rest!r}")
    reply_id, scout, data = parts
    try:
        parsed_reply_id = int(reply_id)
    except ValueError as exc:
        raise EconetError(f"malformed RX_TRANSMIT reply id {reply_id!r}") from exc
    return RxTransmitEvent(reply_id=parsed_reply_id, scout=_b64decode(scout), data=_b64decode(data))


def _parse_rx_immediate(rest: str) -> RxImmediateEvent:
    parts = rest.split()
    if len(parts) != 2:
        raise EconetError(f"malformed RX_IMMEDIATE event: {rest!r}")
    scout, data = parts
    return RxImmediateEvent(scout=_b64decode(scout), data=_b64decode(data))


def _parse_monitor(rest: str) -> MonitorEvent:
    return MonitorEvent(frame=_b64decode(rest))


def _parse_error(rest: str) -> ErrorEvent:
    return ErrorEvent(description=rest)


_EVENT_PARSERS = {
    "STATUS": _parse_status,
    "TX_RESULT": _parse_tx_result,
    "RX_BROADCAST": _parse_rx_broadcast,
    "RX_TRANSMIT": _parse_rx_transmit,
    "RX_IMMEDIATE": _parse_rx_immediate,
    "MONITOR": _parse_monitor,
    "ERROR": _parse_error,
}


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(token: str) -> bytes:
    try:
        return base64.b64decode(token, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EconetError(f"invalid base64 in Piconet event: {token!r}") from exc

"""The outcome of attempting to transmit an Econet packet."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from oaknut.econet.core.packet import EconetPacket


class TransmitOutcome(Enum):
    """How a transmission resolved.

    The union of the failure modes the transports actually report — AUN
    ack/nack/timeout, Piconet ``TX_RESULT`` codes, and PiEconetHAT TX status —
    normalised into one set so applications need not know the transport.
    """

    ACKNOWLEDGED = auto()
    NOT_LISTENING = auto()
    NO_CLOCK = auto()
    LINE_JAMMED = auto()
    TIMEOUT = auto()
    HANDSHAKE_FAILED = auto()
    NETWORK_ERROR = auto()


@dataclass(frozen=True, slots=True)
class TransmitResult:
    """The result of a transmit or immediate operation.

    ``reply`` carries the inline reply for an immediate operation that returns
    one; it is ``None`` otherwise.
    """

    outcome: TransmitOutcome
    reply: EconetPacket | None = None

    @property
    def acknowledged(self) -> bool:
        """True if the transmission was acknowledged by the destination."""
        return self.outcome is TransmitOutcome.ACKNOWLEDGED

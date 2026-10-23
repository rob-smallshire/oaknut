"""Contract for TransmitOutcome and TransmitResult."""

import dataclasses

import pytest
from oaknut.econet.core import TransmitOutcome, TransmitResult


def test_outcomes_exist():
    names = {outcome.name for outcome in TransmitOutcome}
    assert {
        "ACKNOWLEDGED",
        "NOT_LISTENING",
        "NO_CLOCK",
        "LINE_JAMMED",
        "TIMEOUT",
        "HANDSHAKE_FAILED",
        "NETWORK_ERROR",
    } <= names


def test_result_defaults_to_no_reply():
    result = TransmitResult(TransmitOutcome.ACKNOWLEDGED)
    assert result.outcome is TransmitOutcome.ACKNOWLEDGED
    assert result.reply is None


def test_acknowledged_property():
    assert TransmitResult(TransmitOutcome.ACKNOWLEDGED).acknowledged
    assert not TransmitResult(TransmitOutcome.TIMEOUT).acknowledged


def test_is_frozen():
    result = TransmitResult(TransmitOutcome.ACKNOWLEDGED)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.outcome = TransmitOutcome.TIMEOUT

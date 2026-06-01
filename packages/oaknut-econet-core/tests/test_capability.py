"""Contract for TransportCapability."""

from oaknut.econet.core import TransportCapability


def test_capabilities_exist():
    names = {capability.name for capability in TransportCapability}
    assert {"MONITOR", "IMMEDIATE_REPLY", "BROADCAST", "MULTI_NET", "DISCOVERY"} <= names


def test_capabilities_are_distinct():
    assert len(set(TransportCapability)) == len(list(TransportCapability))


def test_usable_in_a_frozenset():
    capabilities = frozenset({TransportCapability.BROADCAST, TransportCapability.MONITOR})
    assert TransportCapability.BROADCAST in capabilities
    assert TransportCapability.DISCOVERY not in capabilities

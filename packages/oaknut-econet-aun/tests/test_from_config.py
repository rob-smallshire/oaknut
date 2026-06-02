"""Contract for AunTransport.from_config."""

import pytest
from oaknut.econet.aun import AunTransport
from oaknut.econet.core import Address, TransportConfigurationError


def test_parses_listen_and_peers():
    transport = AunTransport.from_config(
        name="aun",
        address=Address(0, 254),
        config={
            "listen": "127.0.0.1:40000",
            "peers": [{"address": "0.1", "endpoint": "192.168.1.5:32768"}],
        },
    )
    assert isinstance(transport, AunTransport)
    assert transport.local_station == Address(0, 254)
    assert transport._host == "127.0.0.1"
    assert transport._port == 40000
    assert transport._peers[Address(0, 1)] == ("192.168.1.5", 32768)


def test_defaults_listen_when_absent():
    transport = AunTransport.from_config(name="aun", address=Address(0, 254), config={})
    assert transport._host == "0.0.0.0"
    assert transport._port == 32768


def test_rejects_a_malformed_endpoint():
    with pytest.raises(TransportConfigurationError):
        AunTransport.from_config(name="aun", address=Address(0, 254), config={"listen": "nope"})

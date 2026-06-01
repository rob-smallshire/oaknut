"""Contract for Address and the well-known addressing constants."""

import dataclasses

import pytest
from oaknut.econet.core import (
    BROADCAST_ADDRESS,
    BROADCAST_STATION,
    IMMEDIATE_PORT,
    LOCAL_NET,
    Address,
)


def test_stores_network_and_station():
    address = Address(network=2, station=254)
    assert address.network == 2
    assert address.station == 254


def test_is_broadcast_only_for_station_255():
    assert Address(0, 255).is_broadcast
    assert not Address(0, 254).is_broadcast


def test_is_local_net_only_for_network_0():
    assert Address(0, 1).is_local_net
    assert not Address(1, 1).is_local_net


@pytest.mark.parametrize("network", [-1, 256, 1000])
def test_rejects_out_of_range_network(network):
    with pytest.raises(ValueError):
        Address(network, 1)


@pytest.mark.parametrize("station", [-1, 256, 1000])
def test_rejects_out_of_range_station(station):
    with pytest.raises(ValueError):
        Address(0, station)


def test_is_frozen():
    address = Address(0, 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        address.station = 2


def test_equality_and_hashable():
    assert Address(1, 2) == Address(1, 2)
    assert Address(1, 2) != Address(1, 3)
    assert len({Address(1, 2), Address(1, 2), Address(1, 3)}) == 2


def test_str_is_net_dot_station():
    assert str(Address(0, 254)) == "0.254"


def test_wellknown_constants():
    assert BROADCAST_STATION == 255
    assert LOCAL_NET == 0
    assert IMMEDIATE_PORT == 0x00


def test_broadcast_address_constant_is_broadcast():
    assert BROADCAST_ADDRESS.is_broadcast

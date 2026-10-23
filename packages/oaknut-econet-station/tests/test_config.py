"""Contract for the station-host config loader and build_station.

The build_station tests load the real ``aun`` transport and ``kvstore`` service
plug-ins by name (installed in the workspace); they reference only the names,
not the classes.
"""

import pytest
from oaknut.econet.core import Address
from oaknut.econet.station.config import (
    ServiceConfig,
    StationConfig,
    build_station,
    config_from_flags,
    load_config,
    parse_config,
)
from oaknut.exception import ConfigurationError

_SAMPLE = """
[station]
address = "0.254"
transport = "aun"

[transport]
listen = "0.0.0.0:32768"

[[service]]
name = "kvstore"
"""


# -- parsing ----------------------------------------------------------


def test_parse_minimal():
    config = parse_config({"station": {"address": "0.254", "transport": "aun"}})
    assert config.address == Address(0, 254)
    assert config.transport == "aun"
    assert config.transport_config == {}
    assert config.services == ()


def test_parse_with_transport_and_services():
    config = parse_config(
        {
            "station": {"address": "0.254", "transport": "aun"},
            "transport": {"listen": "0.0.0.0:32768"},
            "service": [{"name": "kvstore"}, {"name": "fileserver", "root": "/srv/x"}],
        }
    )
    assert config.transport_config == {"listen": "0.0.0.0:32768"}
    assert config.services[0] == ServiceConfig("kvstore", {})
    assert config.services[1] == ServiceConfig("fileserver", {"root": "/srv/x"})


def test_parse_missing_station_raises():
    with pytest.raises(ConfigurationError):
        parse_config({})


def test_parse_missing_address_raises():
    with pytest.raises(ConfigurationError):
        parse_config({"station": {"transport": "aun"}})


def test_config_from_flags():
    config = config_from_flags(transport="aun", station="0.254", services=("kvstore",))
    assert config.address == Address(0, 254)
    assert config.transport == "aun"
    assert config.services == (ServiceConfig("kvstore", {}),)


# -- discovery --------------------------------------------------------


def test_load_from_explicit_file(tmp_path):
    path = tmp_path / "econet-host.toml"
    path.write_text(_SAMPLE)
    config, source = load_config(path)
    assert config.address == Address(0, 254)
    assert str(path) in source


def test_load_discovers_a_standalone_file(tmp_path, monkeypatch):
    (tmp_path / "econet-host.toml").write_text(_SAMPLE)
    monkeypatch.chdir(tmp_path)
    config, source = load_config()
    assert config.transport == "aun"
    assert "econet-host.toml" in source


def test_load_discovers_pyproject_section(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.econet-host.station]\naddress = "0.254"\ntransport = "aun"\n'
    )
    monkeypatch.chdir(tmp_path)
    config, source = load_config()
    assert config.address == Address(0, 254)
    assert "tool.econet-host" in source


def test_load_none_found_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigurationError):
        load_config()


# -- building ---------------------------------------------------------


def test_build_station_loads_plugins_by_name():
    config = StationConfig(
        address=Address(0, 254),
        transport="aun",
        transport_config={"listen": "127.0.0.1:40000"},
        services=(ServiceConfig("kvstore", {}),),
    )
    station = build_station(config)
    assert station.address == Address(0, 254)
    assert station.transport.name == "aun"
    assert any(service.name == "kvstore" for service in station._services_by_port.values())


def test_build_station_unknown_transport_raises():
    config = StationConfig(Address(0, 254), "no-such-transport", {}, ())
    with pytest.raises(ConfigurationError):
        build_station(config)


def test_build_station_port_clash_raises():
    config = StationConfig(
        Address(0, 254),
        "aun",
        {},
        (ServiceConfig("kvstore", {}), ServiceConfig("kvstore", {})),
    )
    with pytest.raises(ConfigurationError):
        build_station(config)

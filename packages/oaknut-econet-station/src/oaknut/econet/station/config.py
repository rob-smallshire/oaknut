"""Configuration loading and station building for the econet-host host.

Parses a TOML station config (from a standalone file, a deployment project's
``[tool.econet-host]`` table, or constructed from flags) and builds a
:class:`Station` by loading the named transport and service plug-ins via their
``from_config`` classmethods. No Click here — this is importable without the
``cli`` extra.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from oaknut.econet.core import Address
from oaknut.econet.station.host import Station
from oaknut.exception import ConfigurationError
from oaknut.extension import extension, namespace_for

_TRANSPORT_KIND = "econet.transport"
_SERVICE_KIND = "econet.service"
_STANDALONE_NAME = "econet-host.toml"
_PYPROJECT_SECTION = "econet-host"


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    """A service to host: its plug-in name and its config table."""

    name: str
    config: dict


@dataclass(frozen=True, slots=True)
class StationConfig:
    """A parsed station deployment: address, transport, and services."""

    address: Address
    transport: str
    transport_config: dict
    services: tuple[ServiceConfig, ...]


def parse_config(data: dict) -> StationConfig:
    """Parse a config mapping (the standalone top level, or the
    ``[tool.econet-host]`` table) into a :class:`StationConfig`."""
    try:
        station_table = data["station"]
    except KeyError as exc:
        raise ConfigurationError("config has no [station] table") from exc
    try:
        address = Address.parse(station_table["address"])
        transport = station_table["transport"]
    except KeyError as exc:
        raise ConfigurationError(f"[station] is missing the {exc} key") from exc
    except ValueError as exc:
        raise ConfigurationError(f"[station] address: {exc}") from exc

    services = []
    for entry in data.get("service", []):
        try:
            service_name = entry["name"]
        except KeyError as exc:
            raise ConfigurationError("a [[service]] entry is missing its name") from exc
        services.append(
            ServiceConfig(name=service_name, config={k: v for k, v in entry.items() if k != "name"})
        )
    return StationConfig(
        address=address,
        transport=transport,
        transport_config=dict(data.get("transport", {})),
        services=tuple(services),
    )


def config_from_flags(*, transport: str, station: str, services: tuple[str, ...]) -> StationConfig:
    """Build a config from the flag-only quick path (no per-plug-in options)."""
    try:
        address = Address.parse(station)
    except ValueError as exc:
        raise ConfigurationError(f"--station: {exc}") from exc
    return StationConfig(
        address=address,
        transport=transport,
        transport_config={},
        services=tuple(ServiceConfig(name=name, config={}) for name in services),
    )


def load_config(path: Path | None = None) -> tuple[StationConfig, str]:
    """Load a station config, returning it and a description of its source.

    Discovery order: an explicit *path*; else ``[tool.econet-host]`` in a
    ``pyproject.toml`` found in the cwd or an ancestor; else a conventional
    ``econet-host.toml`` in the cwd. Raises if none is found.
    """
    if path is not None:
        return parse_config(_read_toml(path)), f"file {path}"

    pyproject = _find_pyproject_with_section()
    if pyproject is not None:
        section = _read_toml(pyproject)["tool"][_PYPROJECT_SECTION]
        return parse_config(section), f"{pyproject} [tool.{_PYPROJECT_SECTION}]"

    standalone = Path(_STANDALONE_NAME)
    if standalone.is_file():
        return parse_config(_read_toml(standalone)), f"file {standalone}"

    raise ConfigurationError(
        "no econet-host config found; pass --config, add a config file, "
        "or use the --transport/--station flags"
    )


def build_station(config: StationConfig) -> Station:
    """Build a Station from *config*: load the transport and service plug-ins by
    name (via ``from_config``) and register them. Constructs only — does not open
    the transport."""
    transport_cls = extension(
        _TRANSPORT_KIND, namespace_for(_TRANSPORT_KIND), config.transport,
        exception_type=ConfigurationError,
    )
    transport = transport_cls.from_config(
        name=config.transport, address=config.address, config=config.transport_config
    )
    station = Station(transport, address=config.address)
    for service_config in config.services:
        service_cls = extension(
            _SERVICE_KIND, namespace_for(_SERVICE_KIND), service_config.name,
            exception_type=ConfigurationError,
        )
        service = service_cls.from_config(name=service_config.name, config=service_config.config)
        try:
            station.register(service)
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc
    return station


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"cannot read config {path}: {exc}") from exc


def _find_pyproject_with_section(start: Path | None = None) -> Path | None:
    directory = (start or Path.cwd()).resolve()
    for candidate_dir in (directory, *directory.parents):
        candidate = candidate_dir / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            data = _read_toml(candidate)
        except ConfigurationError:
            continue
        if _PYPROJECT_SECTION in data.get("tool", {}):
            return candidate
    return None

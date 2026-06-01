"""The _aun._udp mDNS station-advertisement convention (Beebium's standard).

This module is the interop-critical TXT-record codec — the format any AUN
implementation (BeebEm, Beebium, PiEconetBridge, real hardware) must agree on.
The mandatory TXT keys are ``version``, ``station``, ``net`` and ``port``;
``net`` must not be defaulted, because net 0 is local-relative and ambiguous
across segments. The ``impl*`` keys are diagnostic only.

It imports no networking library, so it is testable without zeroconf; the live
advertiser/browser (behind the ``mdns`` extra) builds on these functions.
"""

from __future__ import annotations

from dataclasses import dataclass

from oaknut.econet.core import Address, EconetError

#: The vendor-neutral DNS-SD service type for AUN stations.
AUN_SERVICE_TYPE = "_aun._udp.local."

#: The TXT-record schema version this module produces.
TXT_SCHEMA_VERSION = 1

#: Default implementation label used in the service instance name.
DEFAULT_IMPL = "oaknut"

_MANDATORY_KEYS = ("version", "station", "net", "port")


@dataclass(frozen=True, slots=True)
class AunService:
    """An advertised AUN station: its address, UDP port, and optional impl info."""

    station: Address
    udp_port: int
    impl: str | None = None
    impl_version: str | None = None
    impl_identity: str | None = None


def build_txt(service: AunService) -> dict[str, bytes]:
    """Build the mDNS TXT record advertising *service*."""
    txt: dict[str, bytes] = {
        "version": str(TXT_SCHEMA_VERSION).encode(),
        "station": str(service.station.station).encode(),
        "net": str(service.station.network).encode(),
        "port": str(service.udp_port).encode(),
    }
    if service.impl is not None:
        txt["impl"] = service.impl.encode()
    if service.impl_version is not None:
        txt["impl-version"] = service.impl_version.encode()
    if service.impl_identity is not None:
        txt["impl-identity"] = service.impl_identity.encode()
    return txt


def parse_txt(txt: dict) -> AunService:
    """Parse an mDNS TXT record into an :class:`AunService`.

    Accepts ``str`` or ``bytes`` keys and values (zeroconf supplies bytes).
    Raises :class:`EconetError` on a missing mandatory key or a malformed value.
    """
    fields = {_as_str(key): _as_str(value) for key, value in txt.items()}
    for required in _MANDATORY_KEYS:
        if fields.get(required) is None:
            raise EconetError(f"AUN mDNS TXT missing mandatory key {required!r}")
    try:
        net = int(fields["net"])
        station = int(fields["station"])
        udp_port = int(fields["port"])
    except ValueError as exc:
        raise EconetError(f"AUN mDNS TXT has a non-integer value: {exc}") from exc
    try:
        address = Address(net, station)
    except ValueError as exc:
        raise EconetError(f"AUN mDNS TXT has an out-of-range address: {exc}") from exc
    return AunService(
        station=address,
        udp_port=udp_port,
        impl=fields.get("impl"),
        impl_version=fields.get("impl-version"),
        impl_identity=fields.get("impl-identity"),
    )


def instance_name(service: AunService, impl: str | None = None) -> str:
    """The DNS-SD instance name for *service*, e.g. ``oaknut-32._aun._udp.local.``."""
    label = impl or service.impl or DEFAULT_IMPL
    return f"{label}-{service.station.station}.{AUN_SERVICE_TYPE}"


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode()
    return str(value)

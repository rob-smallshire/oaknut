"""Contract for the _aun._udp mDNS TXT codec (the vendor-neutral standard)."""

import pytest
from oaknut.econet.aun.discovery import (
    AUN_SERVICE_TYPE,
    TXT_SCHEMA_VERSION,
    AunService,
    build_txt,
    instance_name,
    parse_txt,
)
from oaknut.econet.core import Address, EconetError


def test_service_type_is_the_vendor_neutral_name():
    assert AUN_SERVICE_TYPE == "_aun._udp.local."


def test_build_txt_includes_the_mandatory_keys():
    service = AunService(Address(0, 254), udp_port=32768)
    txt = build_txt(service)
    assert txt["version"] == str(TXT_SCHEMA_VERSION).encode()
    assert txt["station"] == b"254"
    assert txt["net"] == b"0"
    assert txt["port"] == b"32768"
    assert "impl" not in txt


def test_build_txt_includes_optional_impl_fields():
    service = AunService(
        Address(1, 42),
        udp_port=40000,
        impl="oaknut",
        impl_version="12.5.3",
        impl_identity="abc",
    )
    txt = build_txt(service)
    assert txt["impl"] == b"oaknut"
    assert txt["impl-version"] == b"12.5.3"
    assert txt["impl-identity"] == b"abc"


def test_parse_round_trips_a_service():
    service = AunService(Address(3, 200), udp_port=33000, impl="oaknut")
    assert parse_txt(build_txt(service)) == service


def test_parse_accepts_bytes_keys_as_zeroconf_supplies_them():
    txt = {b"version": b"1", b"station": b"2", b"net": b"0", b"port": b"32768"}
    service = parse_txt(txt)
    assert service.station == Address(0, 2)
    assert service.udp_port == 32768


@pytest.mark.parametrize("missing", ["version", "station", "net", "port"])
def test_parse_requires_each_mandatory_key(missing):
    txt = {"version": b"1", "station": b"2", "net": b"0", "port": b"32768"}
    del txt[missing]
    with pytest.raises(EconetError):
        parse_txt(txt)


def test_parse_rejects_non_integer_values():
    txt = {"version": b"1", "station": b"x", "net": b"0", "port": b"32768"}
    with pytest.raises(EconetError):
        parse_txt(txt)


def test_parse_rejects_out_of_range_address():
    txt = {"version": b"1", "station": b"999", "net": b"0", "port": b"32768"}
    with pytest.raises(EconetError):
        parse_txt(txt)


def test_instance_name_uses_impl_and_station():
    service = AunService(Address(0, 32), udp_port=32768, impl="oaknut")
    assert instance_name(service) == "oaknut-32._aun._udp.local."

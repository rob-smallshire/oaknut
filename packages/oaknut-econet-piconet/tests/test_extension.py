"""The Piconet transport is discoverable and loadable on the extension axis."""

from oaknut.econet.core import Address
from oaknut.econet.piconet import FakePiconet, PiconetTransport
from oaknut.extension import create_extension, list_extensions, namespace_for


def test_registered_on_the_transport_axis():
    assert "piconet" in list_extensions(namespace_for("econet.transport"))


def test_loadable_via_create_extension():
    transport = create_extension(
        "econet.transport",
        namespace_for("econet.transport"),
        "piconet",
        link=FakePiconet(),
        local_station=Address(0, 1),
    )
    assert isinstance(transport, PiconetTransport)
    assert transport.name == "piconet"

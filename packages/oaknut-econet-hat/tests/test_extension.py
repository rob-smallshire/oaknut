"""The HAT transport is discoverable and loadable on the extension axis."""

from oaknut.econet.core import Address
from oaknut.econet.hat import FakeKernelDevice, HatTransport
from oaknut.extension import create_extension, list_extensions, namespace_for


def test_registered_on_the_transport_axis():
    assert "hat" in list_extensions(namespace_for("econet.transport"))


def test_loadable_via_create_extension():
    transport = create_extension(
        "econet.transport",
        namespace_for("econet.transport"),
        "hat",
        device=FakeKernelDevice(),
        local_station=Address(0, 1),
    )
    assert isinstance(transport, HatTransport)
    assert transport.name == "hat"

"""Contract for PiconetTransport.from_config."""

from oaknut.econet.core import Address
from oaknut.econet.piconet import PiconetTransport, SerialPicoLink


def test_builds_a_serial_link_from_the_port():
    transport = PiconetTransport.from_config(
        name="piconet", address=Address(0, 1), config={"port": "/dev/ttyACM0"}
    )
    assert isinstance(transport, PiconetTransport)
    assert transport.local_station == Address(0, 1)
    assert isinstance(transport._link, SerialPicoLink)
    assert transport._link._port == "/dev/ttyACM0"


def test_auto_detects_when_no_port_given():
    transport = PiconetTransport.from_config(name="piconet", address=Address(0, 1), config={})
    assert isinstance(transport._link, SerialPicoLink)
    assert transport._link._port is None  # auto-detect by USB id at open()

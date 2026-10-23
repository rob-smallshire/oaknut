"""Contract for HatTransport.from_config."""

from oaknut.econet.core import Address
from oaknut.econet.hat import EconetGpioDevice, HatTransport


def test_builds_a_gpio_device_from_the_path():
    transport = HatTransport.from_config(
        name="hat", address=Address(0, 254), config={"device": "/dev/econet-gpio"}
    )
    assert isinstance(transport, HatTransport)
    assert transport.local_station == Address(0, 254)
    assert isinstance(transport._device, EconetGpioDevice)
    assert transport._device._path == "/dev/econet-gpio"


def test_uses_the_default_device_path_when_absent():
    transport = HatTransport.from_config(name="hat", address=Address(0, 254), config={})
    assert isinstance(transport._device, EconetGpioDevice)
    assert transport._device._path == "/dev/econet-gpio"

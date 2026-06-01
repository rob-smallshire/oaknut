"""Contract for the oaknut-econet error hierarchy."""

import pytest
from oaknut.econet.core import EconetError, TransportConfigurationError
from oaknut.exception import ConfigurationError, DataError, OaknutException


def test_econet_error_is_a_data_error():
    assert issubclass(EconetError, DataError)
    assert issubclass(EconetError, OaknutException)


def test_transport_configuration_error_is_a_configuration_error():
    assert issubclass(TransportConfigurationError, ConfigurationError)


def test_econet_error_raisable_and_caught_as_data_error():
    with pytest.raises(DataError):
        raise EconetError("malformed packet")


def test_transport_configuration_error_raisable_as_configuration_error():
    with pytest.raises(ConfigurationError):
        raise TransportConfigurationError("no such device")

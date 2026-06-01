"""The oaknut-econet error hierarchy, slotted into oaknut.exception."""

from __future__ import annotations

from oaknut.exception import ConfigurationError, DataError


class EconetError(DataError):
    """Base for Econet wire/protocol data faults.

    A malformed AUN datagram, an unparseable serial frame, or any other bad
    data arriving from the network is a :class:`~oaknut.exception.DataError`.
    """


class TransportConfigurationError(ConfigurationError):
    """A transport could not be configured or opened.

    An unknown transport name, a missing or unopenable device, or an invalid
    station number is an environment/setup problem rather than bad input or a
    library bug — hence a :class:`~oaknut.exception.ConfigurationError`.
    """

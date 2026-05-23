"""Tests for the OaknutException hierarchy and exit-code resolution."""

from __future__ import annotations

import pytest
from exit_codes import ExitCode
from oaknut.exception import (
    ConfigurationError,
    DataError,
    InternalError,
    OaknutException,
    exit_code_for,
)


class TestCategoryDefaults:
    """Each category exposes its sysexits.h default through `.exit_code`."""

    def test_data_error_default(self) -> None:
        assert DataError("nope").exit_code is ExitCode.DATA_ERR

    def test_configuration_error_default(self) -> None:
        assert ConfigurationError("bad cfg").exit_code is ExitCode.CONFIG

    def test_internal_error_default(self) -> None:
        assert InternalError("bug").exit_code is ExitCode.SOFTWARE

    def test_root_default(self) -> None:
        # The root is meant to be subclassed, but if anyone instantiates
        # it directly the fallback should be SOFTWARE so the resulting
        # exit code is at least non-zero and not misleadingly DATA_ERR.
        assert OaknutException("raw").exit_code is ExitCode.SOFTWARE


class TestInstanceOverride:
    """A constructor `exit_code=` overrides the class default for one
    instance, without needing a private subclass per variant."""

    def test_override_takes_precedence(self) -> None:
        exc = DataError("missing", exit_code=ExitCode.OS_FILE)
        assert exc.exit_code is ExitCode.OS_FILE

    def test_override_is_per_instance(self) -> None:
        overridden = DataError("missing", exit_code=ExitCode.OS_FILE)
        default = DataError("missing")
        assert overridden.exit_code is ExitCode.OS_FILE
        assert default.exit_code is ExitCode.DATA_ERR


class TestSubclassDefault:
    """A subclass can override `_exit_code` to pin a more specific code
    for every instance of that class. This is the canonical pattern
    used by oaknut-file's FSError tree."""

    class _PathNotFound(DataError):
        _exit_code = ExitCode.OS_FILE

    def test_subclass_uses_its_own_default(self) -> None:
        assert self._PathNotFound("hi").exit_code is ExitCode.OS_FILE

    def test_subclass_default_still_overridable(self) -> None:
        exc = self._PathNotFound("hi", exit_code=ExitCode.NO_PERM)
        assert exc.exit_code is ExitCode.NO_PERM


class TestExitCodeFor:
    """The free function form is what CLI boundary code uses when it
    only has an exception object, not a known type."""

    def test_oaknut_exception_returns_its_code(self) -> None:
        exc = DataError("x", exit_code=ExitCode.OS_FILE)
        assert exit_code_for(exc) is ExitCode.OS_FILE

    def test_non_oaknut_exception_falls_back_to_software(self) -> None:
        # A library that raises a stdlib exception by accident still
        # gets a non-zero code if the boundary catches it explicitly.
        assert exit_code_for(ValueError("not ours")) is ExitCode.SOFTWARE


class TestInheritance:
    """Sanity: the category structure is what callers expect."""

    def test_categories_share_root(self) -> None:
        assert issubclass(DataError, OaknutException)
        assert issubclass(ConfigurationError, OaknutException)
        assert issubclass(InternalError, OaknutException)

    def test_categories_are_distinct(self) -> None:
        assert not issubclass(DataError, ConfigurationError)
        assert not issubclass(ConfigurationError, InternalError)
        assert not issubclass(DataError, InternalError)

    def test_caught_as_OaknutException(self) -> None:
        with pytest.raises(OaknutException):
            raise DataError("test")

"""Tests for the handled_errors boundary helper."""

from __future__ import annotations

import signal

import pytest
from exit_codes import ExitCode
from oaknut.exception import (
    ConfigurationError,
    DataError,
    InternalError,
    handled_errors,
)


def _capture_exit():
    """Return (captured_codes, exit_func) so tests can intercept sys.exit."""
    captured: list[int] = []
    return captured, captured.append


def _capture_printer():
    """Return (lines, printer) capturing (text, is_continuation) pairs."""
    lines: list[tuple[str, bool]] = []

    def printer(text: str, is_continuation: bool) -> None:
        lines.append((text, is_continuation))

    return lines, printer


class TestNormalCompletion:
    def test_no_error_does_not_exit(self) -> None:
        codes, exit_func = _capture_exit()
        with handled_errors(exit_func=exit_func):
            pass
        assert codes == []


class TestDataError:
    def test_caught_and_exits_with_data_code(self) -> None:
        codes, exit_func = _capture_exit()
        lines, printer = _capture_printer()
        with handled_errors(printer, exit_func=exit_func):
            raise DataError("bad input")
        assert codes == [int(ExitCode.DATA_ERR)]
        assert lines == [("bad input", False)]

    def test_per_instance_override_is_honoured(self) -> None:
        codes, exit_func = _capture_exit()
        _, printer = _capture_printer()
        with handled_errors(printer, exit_func=exit_func):
            raise DataError("missing", exit_code=ExitCode.OS_FILE)
        assert codes == [int(ExitCode.OS_FILE)]


class TestConfigurationError:
    def test_caught_and_exits_with_config_code(self) -> None:
        codes, exit_func = _capture_exit()
        _, printer = _capture_printer()
        with handled_errors(printer, exit_func=exit_func):
            raise ConfigurationError("bad config")
        assert codes == [int(ExitCode.CONFIG)]


class TestInternalError:
    """InternalError propagates — the traceback is the report-an-issue signal."""

    def test_propagates_unchanged(self) -> None:
        codes, exit_func = _capture_exit()
        with pytest.raises(InternalError, match="oops"):
            with handled_errors(exit_func=exit_func):
                raise InternalError("oops")
        # No call to exit_func because the error propagated.
        assert codes == []


class TestOtherExceptions:
    """Anything outside the OaknutException tree is left alone."""

    def test_value_error_propagates(self) -> None:
        codes, exit_func = _capture_exit()
        with pytest.raises(ValueError):
            with handled_errors(exit_func=exit_func):
                raise ValueError("not ours")
        assert codes == []


class TestKeyboardInterrupt:
    def test_caught_and_exits_with_128_plus_sigint(self) -> None:
        codes, exit_func = _capture_exit()
        _, printer = _capture_printer()
        with handled_errors(printer, exit_func=exit_func):
            raise KeyboardInterrupt
        assert codes == [128 + signal.SIGINT]


class TestExceptionGroup:
    """The except* branches in handled_errors mean an ExceptionGroup
    of categorised errors is also handled correctly."""

    def test_group_of_data_errors_uses_first_code(self) -> None:
        codes, exit_func = _capture_exit()
        lines, printer = _capture_printer()
        with handled_errors(printer, exit_func=exit_func):
            raise ExceptionGroup(
                "two errors",
                [
                    DataError("first", exit_code=ExitCode.OS_FILE),
                    DataError("second", exit_code=ExitCode.NO_PERM),
                ],
            )
        # First-wins: deterministic, matches reading order.
        assert codes == [int(ExitCode.OS_FILE)]
        # Both errors were rendered.
        assert ("first", False) in lines
        assert ("second", False) in lines

    def test_mixed_group_with_internal_error_propagates_partial(self) -> None:
        # Python's except* automatically splits the group: the
        # DataError half is consumed by our handler, the InternalError
        # half propagates as its own group.
        codes, exit_func = _capture_exit()
        _, printer = _capture_printer()
        with pytest.raises(ExceptionGroup) as exc_info:
            with handled_errors(printer, exit_func=exit_func):
                raise ExceptionGroup(
                    "mixed",
                    [DataError("data"), InternalError("internal")],
                )
        # The propagated group should contain only the internal half.
        leaves = [type(leaf).__name__ for leaf in exc_info.value.exceptions]
        assert leaves == ["InternalError"]


class TestDebugMode:
    """In debug mode, even DataError gets re-raised after being printed
    so developers see the full traceback."""

    def test_data_error_reraised_after_printing(self) -> None:
        codes, exit_func = _capture_exit()
        lines, printer = _capture_printer()
        with pytest.raises(DataError, match="for the dev"):
            with handled_errors(printer, exit_func=exit_func, debug=True):
                raise DataError("for the dev")
        # Printed once before re-raising.
        assert lines == [("for the dev", False)]
        # No exit call because we re-raised.
        assert codes == []

    def test_internal_error_unaffected_by_debug(self) -> None:
        codes, exit_func = _capture_exit()
        _, printer = _capture_printer()
        with pytest.raises(InternalError):
            with handled_errors(printer, exit_func=exit_func, debug=True):
                raise InternalError("propagates either way")
        assert codes == []


class TestDecoratorUsage:
    """contextmanager from contextlib produces ContextDecorator, so the
    helper is usable as @handled_errors() too."""

    def test_decorates_a_function(self) -> None:
        codes, exit_func = _capture_exit()
        _, printer = _capture_printer()

        @handled_errors(printer, exit_func=exit_func)
        def boom():
            raise DataError("decorated")

        boom()
        assert codes == [int(ExitCode.DATA_ERR)]

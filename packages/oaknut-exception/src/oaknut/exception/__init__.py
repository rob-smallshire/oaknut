"""Categorised exceptions and CLI error-reporting boundary for oaknut.

This module supplies three things every ``oaknut-*`` library and CLI
shares:

1. A small exception hierarchy — :class:`OaknutException` root and the
   :class:`DataError`/:class:`ConfigurationError`/:class:`InternalError`
   category subclasses. Each carries a stable :class:`ExitCode` so the
   library decides how an error classifies; the CLI just observes.

2. A :func:`handled_errors` context manager (also usable as a
   decorator, via :class:`contextlib.ContextDecorator`) that catches
   :class:`DataError` and :class:`ConfigurationError`, prints them via
   a caller-supplied printer, and exits with the most appropriate
   :class:`ExitCode`. :class:`InternalError` and other exceptions
   propagate so their tracebacks reach the user. ``KeyboardInterrupt``
   exits with the conventional ``128 + SIGINT`` status.

3. A :func:`render_error` helper that walks an exception's ``__cause__``
   chain and any ``__notes__`` so the boundary printer can format the
   full story rather than just the leaf message.

The design is intentionally close to ``demonstrable-exception`` — we
have permission to borrow the shape — with a few opinionated
refinements: per-instance exit-code override, deterministic
first-wins selection across exception groups, an explicit
:func:`render_error` separation, and a printer protocol that is easy
to wrap with format-aware adapters at the CLI layer.
"""

from __future__ import annotations

import signal
import sys
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from typing import Iterator, Optional

from exit_codes import ExitCode

__version__ = "12.15.1"

__all__ = [
    "OaknutException",
    "DataError",
    "ConfigurationError",
    "InternalError",
    "Printer",
    "handled_errors",
    "render_error",
    "exit_code_for",
]


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class OaknutException(Exception):
    """Base class for every domain exception in the oaknut family.

    Do not raise this directly — raise one of the category subclasses
    (:class:`DataError`, :class:`ConfigurationError`,
    :class:`InternalError`) or a domain-specific class that derives
    from one of them.

    Every instance has an :attr:`exit_code` of type :class:`ExitCode`.
    The class attribute :attr:`_exit_code` provides the default for a
    given category or subclass; a constructor argument overrides it for
    a single instance::

        raise DataError("path not found: $.HELLO", exit_code=ExitCode.OS_FILE)

    The override is what lets a library raise the right BSD code for a
    specific case (path-not-found vs. permission-denied vs. file-full)
    without needing a private exception class for every variant.
    """

    #: The default :class:`ExitCode` for this class. Subclasses override.
    _exit_code: ExitCode = ExitCode.SOFTWARE

    def __init__(self, *args: object, exit_code: Optional[ExitCode] = None) -> None:
        super().__init__(*args)
        self._instance_exit_code: Optional[ExitCode] = exit_code

    @property
    def exit_code(self) -> ExitCode:
        """The :class:`ExitCode` that should accompany this error.

        The per-instance override, if one was passed to the
        constructor; otherwise the class default.
        """
        if self._instance_exit_code is not None:
            return self._instance_exit_code
        return self._exit_code


class DataError(OaknutException):
    """An error caused by the *data* the operation was asked to act on.

    Covers both user input (a path that doesn't exist, an invalid name,
    a file the user pointed at) and on-disc data (a corrupted catalogue,
    an inconsistent free-space map). The CLI boundary prints these
    without a stack trace — they are not bugs, they are problems with
    the input.
    """

    _exit_code = ExitCode.DATA_ERR


class ConfigurationError(OaknutException):
    """An error caused by a runtime-environment configuration issue.

    Things like "configured cache directory is not writable", "required
    extension binary not on PATH", or "config file references a missing
    profile". The CLI boundary prints these without a stack trace —
    they are problems with the *setup*, not the *data* or the code.
    """

    _exit_code = ExitCode.CONFIG


class InternalError(OaknutException):
    """An error caused by something going unexpectedly wrong inside the library.

    The CLI boundary lets these propagate with a stack trace because
    that is the report-an-issue signal: there is no clean way to
    explain it to a user — the maintainers need the traceback to fix
    the root cause.
    """

    _exit_code = ExitCode.SOFTWARE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


#: A printer callable. Takes the rendered error message string and a
#: hint about whether the rendering came from the leaf exception
#: (``False``) or a chained cause / note (``True``). CLIs typically
#: render leaves in red and continuations in a muted colour.
Printer = Callable[[str, bool], None]


def exit_code_for(exc: BaseException) -> ExitCode:
    """Return the :class:`ExitCode` for *exc*.

    For :class:`OaknutException` instances, returns the instance's
    :attr:`~OaknutException.exit_code`. For everything else, returns
    :data:`ExitCode.SOFTWARE` so an unexpected exception still maps to
    a sensible non-zero code if a caller chooses to swallow it.
    """
    if isinstance(exc, OaknutException):
        return exc.exit_code
    return ExitCode.SOFTWARE


def render_error(exc: BaseException) -> Iterator[tuple[str, bool]]:
    """Yield ``(line, is_continuation)`` pairs for *exc* and its causes.

    The leaf exception's ``str()`` is yielded first with
    ``is_continuation=False``. Any ``__notes__`` (PEP 678, Python 3.11+)
    follow with ``is_continuation=True``. If the exception was raised
    with ``raise X from Y``, the cause chain is walked and rendered
    recursively, each line prefixed with ``"caused by: "``.

    Callers feed each ``(line, is_continuation)`` pair to a
    :data:`Printer` and the printer decides the styling — the splitting
    is the same regardless of whether the printer is colour-aware,
    pipe-friendly, or JSON.
    """
    yield str(exc) or type(exc).__name__, False
    for note in getattr(exc, "__notes__", ()):
        yield str(note), True

    cause = exc.__cause__
    while cause is not None:
        yield f"caused by: {cause or type(cause).__name__}", True
        for note in getattr(cause, "__notes__", ()):
            yield str(note), True
        cause = cause.__cause__


# ---------------------------------------------------------------------------
# handled_errors — the CLI boundary helper
# ---------------------------------------------------------------------------


DEFAULT_EXIT_CODE = ExitCode.SOFTWARE


def _default_printer(line: str, _is_continuation: bool) -> None:
    print(line, file=sys.stderr)


@contextmanager
def handled_errors(
    printer: Optional[Printer] = None,
    *,
    exit_func: Callable[[int], None] = sys.exit,
    debug: bool = False,
) -> Iterator[None]:
    """Catch :class:`DataError`/:class:`ConfigurationError`, print, exit.

    Use at the CLI boundary, either as a context manager wrapping a
    body of work::

        with handled_errors(print_error):
            do_the_work()

    or — because :func:`contextlib.contextmanager` produces a
    :class:`contextlib.ContextDecorator` — as a decorator on a Click
    command callback::

        @handled_errors(print_error)
        def cmd(...): ...

    Behaviour:

    - :class:`DataError` / :class:`ConfigurationError` and any
      :class:`ExceptionGroup` containing them are caught, each leaf
      rendered via :func:`render_error`, and the process is exited
      with the **first** leaf's exit code (deterministic; matches the
      order errors were raised).
    - :class:`InternalError` and any other exception propagate.
    - ``KeyboardInterrupt`` exits with ``128 + SIGINT`` after printing
      itself.
    - When *debug* is ``True``, :class:`DataError` and
      :class:`ConfigurationError` are *re-raised* after being printed
      so the caller still sees the full Python traceback — useful
      during development; off by default for users.

    *printer* defaults to a plain stderr writer. *exit_func* defaults
    to :func:`sys.exit`; tests inject a custom function to capture the
    code without terminating the test runner.
    """
    if printer is None:
        printer = _default_printer

    pending_exit: Optional[int] = None
    pending_reraise: Optional[BaseException] = None

    try:
        yield
    except* (DataError, ConfigurationError) as group:
        leaves = list(_iter_leaves(group))
        for leaf in leaves:
            for line, is_continuation in render_error(leaf):
                printer(line, is_continuation)
        if debug and leaves:
            pending_reraise = leaves[0]
        else:
            # First-wins: the first leaf's code, falling back to the
            # category default if somehow none classify.
            first_code = next(
                (exit_code_for(leaf) for leaf in leaves if isinstance(leaf, OaknutException)),
                DEFAULT_EXIT_CODE,
            )
            pending_exit = int(first_code)
    except* KeyboardInterrupt as group:
        for leaf in _iter_leaves(group):
            for line, is_continuation in render_error(leaf):
                printer(line, is_continuation)
        pending_exit = 128 + signal.SIGINT

    if pending_reraise is not None:
        raise pending_reraise
    if pending_exit is not None:
        exit_func(pending_exit)


def _iter_leaves(group: BaseExceptionGroup) -> Iterable[BaseException]:
    """Yield leaf exceptions from a (possibly nested) exception group."""
    for exc in group.exceptions:
        if isinstance(exc, BaseExceptionGroup):
            yield from _iter_leaves(exc)
        else:
            yield exc

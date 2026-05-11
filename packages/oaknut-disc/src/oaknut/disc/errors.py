"""CLI error reporting: FSError -> ClickException with stable exit codes.

The library layers (``oaknut.file``, ``oaknut.dfs``, ``oaknut.adfs``,
``oaknut.afs``) raise rich subclasses of :class:`FSError` for every
expected failure mode -- directory full, disc full, locked file, path
not found, malformed structure, and so on. Letting those propagate
out of a CLI command produces a Python traceback, which is the wrong
shape for an end-user tool: the user wants a one-line diagnostic and
a non-zero exit code their script can branch on.

The :func:`handles_fs_errors` decorator wraps a Click command callback
to catch any :class:`FSError`, look up a stable exit code for its
class (walking the MRO so subclasses inherit their parent's code
unless overridden), and re-raise as :class:`FSClickException`. Any
other exception (programming bugs, ``KeyboardInterrupt``, plain
``click.ClickException``) propagates unchanged.

Exit codes are documented in ``docs/cli-design.md``. The numeric
table below is the single source of truth; new error classes get a
code by adding one entry to :data:`_EXCEPTION_EXIT_CODES`.
"""

from __future__ import annotations

import functools
from typing import Callable, TypeVar

import click

from oaknut.file.exceptions import FSError

# ---------------------------------------------------------------------------
# Exit codes -- stable across the lifetime of the CLI. Scripts MAY branch
# on these.
# ---------------------------------------------------------------------------

EXIT_GENERIC = 1
EXIT_PATH_NOT_FOUND = 10
EXIT_ALREADY_EXISTS = 11
EXIT_DIRECTORY_FULL = 12
EXIT_DISC_FULL = 13
EXIT_LOCKED = 14
EXIT_ACCESS_DENIED = 15
EXIT_NOT_EMPTY = 16
EXIT_FORMAT_ERROR = 20
EXIT_INVALID_NAME = 21
EXIT_HOST_IO = 22
EXIT_REPARTITION = 30
EXIT_MERGE_CONFLICT = 31


# ---------------------------------------------------------------------------
# Class -> exit code mapping. Stored as (dotted_class_path, code) so the
# library packages stay optional at import time; classes are resolved
# lazily on first lookup. The MRO walk in `exit_code_for` makes subclasses
# inherit their parent's code unless they have their own entry.
# ---------------------------------------------------------------------------

_CLASS_PATH_EXIT_CODES: tuple[tuple[str, int], ...] = (
    # --- DFS ---
    ("oaknut.dfs.exceptions.CatalogFullError", EXIT_DIRECTORY_FULL),
    ("oaknut.dfs.exceptions.FileExistsError", EXIT_ALREADY_EXISTS),
    ("oaknut.dfs.exceptions.CatalogReadError", EXIT_FORMAT_ERROR),
    ("oaknut.dfs.exceptions.DiskFullError", EXIT_DISC_FULL),
    ("oaknut.dfs.exceptions.FileLocked", EXIT_LOCKED),
    ("oaknut.dfs.exceptions.InvalidFormatError", EXIT_FORMAT_ERROR),
    # --- ADFS ---
    ("oaknut.adfs.exceptions.ADFSDirectoryFullError", EXIT_DIRECTORY_FULL),
    ("oaknut.adfs.exceptions.ADFSDirectoryError", EXIT_FORMAT_ERROR),
    ("oaknut.adfs.exceptions.ADFSDiscFullError", EXIT_DISC_FULL),
    ("oaknut.adfs.exceptions.ADFSMapError", EXIT_FORMAT_ERROR),
    ("oaknut.adfs.exceptions.ADFSPathError", EXIT_PATH_NOT_FOUND),
    ("oaknut.adfs.exceptions.ADFSFileLockedError", EXIT_LOCKED),
    # --- AFS ---
    ("oaknut.afs.exceptions.AFSDirectoryFullError", EXIT_DIRECTORY_FULL),
    ("oaknut.afs.exceptions.AFSDirectoryEntryExistsError", EXIT_ALREADY_EXISTS),
    ("oaknut.afs.exceptions.AFSDirectoryEntryNotFoundError", EXIT_PATH_NOT_FOUND),
    ("oaknut.afs.exceptions.AFSDirectoryNotEmptyError", EXIT_NOT_EMPTY),
    ("oaknut.afs.exceptions.AFSPathError", EXIT_PATH_NOT_FOUND),
    ("oaknut.afs.exceptions.AFSAccessDeniedError", EXIT_ACCESS_DENIED),
    ("oaknut.afs.exceptions.AFSFileLockedError", EXIT_LOCKED),
    ("oaknut.afs.exceptions.AFSInsufficientSpaceError", EXIT_DISC_FULL),
    ("oaknut.afs.exceptions.AFSQuotaExceededError", EXIT_DISC_FULL),
    ("oaknut.afs.exceptions.AFSFormatError", EXIT_FORMAT_ERROR),
    ("oaknut.afs.exceptions.AFSInitSpecError", EXIT_INVALID_NAME),
    ("oaknut.afs.exceptions.AFSRepartitionError", EXIT_REPARTITION),
    ("oaknut.afs.exceptions.AFSMergeConflictError", EXIT_MERGE_CONFLICT),
    ("oaknut.afs.exceptions.AFSHostImportError", EXIT_HOST_IO),
)


def _resolve_class(dotted: str) -> type | None:
    """Import the module and return the class, or ``None`` if absent.

    Returns ``None`` rather than raising so the mapping stays resilient
    when a class is renamed or removed in a library package; the only
    consequence is that the fallback ``EXIT_GENERIC`` will be used.
    """
    module_name, _, class_name = dotted.rpartition(".")
    try:
        module = __import__(module_name, fromlist=[class_name])
    except ImportError:
        return None
    return getattr(module, class_name, None)


_RESOLVED_EXIT_CODES: dict[type, int] | None = None


def _exit_code_table() -> dict[type, int]:
    global _RESOLVED_EXIT_CODES
    if _RESOLVED_EXIT_CODES is None:
        table: dict[type, int] = {}
        for dotted, code in _CLASS_PATH_EXIT_CODES:
            cls = _resolve_class(dotted)
            if cls is not None:
                table[cls] = code
        _RESOLVED_EXIT_CODES = table
    return _RESOLVED_EXIT_CODES


def exit_code_for(exc: BaseException) -> int:
    """Return the exit code for an ``FSError`` instance.

    Walks the MRO from most-specific to least-specific so subclasses
    inherit their parent's code automatically. Falls back to
    :data:`EXIT_GENERIC` if no ancestor is in the table.
    """
    table = _exit_code_table()
    for ancestor in type(exc).__mro__:
        code = table.get(ancestor)
        if code is not None:
            return code
    return EXIT_GENERIC


# ---------------------------------------------------------------------------
# FSClickException -- a ClickException with a settable exit code.
# ---------------------------------------------------------------------------


class FSClickException(click.ClickException):
    """``click.ClickException`` with a per-category exit code.

    Click's stock ``ClickException`` hard-codes ``exit_code = 1``; we
    override it instance-by-instance so each FSError category surfaces
    its own stable code.
    """

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# ---------------------------------------------------------------------------
# Decorator.
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., object])


def handles_fs_errors(func: F) -> F:
    """Convert :class:`FSError` raised by the wrapped command to ``FSClickException``.

    Apply between ``@cli.command()``/``@click.argument`` and the
    function definition, e.g.::

        @cli.command()
        @click.argument("image", ...)
        @handles_fs_errors
        def cp(...): ...

    Any non-``FSError`` exception (including bugs and
    ``KeyboardInterrupt``) propagates unchanged so genuine programming
    errors still produce a traceback.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FSError as exc:
            message = str(exc) or type(exc).__name__
            raise FSClickException(message, exit_code_for(exc)) from exc

    return wrapper  # type: ignore[return-value]

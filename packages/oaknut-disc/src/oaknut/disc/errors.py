"""CLI error reporting: FSError -> ClickException with stable exit codes.

The library layers (``oaknut.file``, ``oaknut.dfs``, ``oaknut.adfs``,
``oaknut.afs``) raise rich subclasses of :class:`FSError` for every
expected failure mode -- directory full, disc full, locked file, path
not found, malformed structure, and so on. Letting those propagate
out of a CLI command produces a Python traceback, which is the wrong
shape for an end-user tool: the user wants a one-line diagnostic and
a non-zero exit code their script can branch on.

The :func:`handles_fs_errors` decorator wraps a Click command callback
to catch any :class:`FSError`, look up an :class:`ExitCode` for its
class (walking the MRO so subclasses inherit their parent's code
unless overridden), and re-raise as :class:`FSClickException`. Any
other exception (programming bugs, ``KeyboardInterrupt``, plain
``click.ClickException``) propagates unchanged.

Exit codes come from the standard BSD ``sysexits.h`` set, exposed by
the ``exit-codes`` package as :class:`ExitCode`. The mapping below is
the single source of truth; new error classes get a code by adding
one entry to :data:`_CLASS_PATH_EXIT_CODES`. The full table and its
script-facing semantics are documented in
``docs/manual/cli/conventions/exit-codes.rst``.
"""

from __future__ import annotations

import functools
from typing import Callable, TypeVar

import click
from exit_codes import ExitCode
from oaknut.file.exceptions import FSError

# ---------------------------------------------------------------------------
# FSError class -> ExitCode mapping.
#
# Stored as (dotted_class_path, code) so the library packages stay
# optional at import time; classes are resolved lazily on first lookup.
# The MRO walk in `exit_code_for` makes subclasses inherit their
# parent's code unless they have their own entry.
# ---------------------------------------------------------------------------

_CLASS_PATH_EXIT_CODES: tuple[tuple[str, ExitCode], ...] = (
    # --- DFS ---
    ("oaknut.dfs.exceptions.CatalogFullError", ExitCode.CANT_CREATE),
    ("oaknut.dfs.exceptions.FileExistsError", ExitCode.CANT_CREATE),
    ("oaknut.dfs.exceptions.CatalogReadError", ExitCode.DATA_ERR),
    ("oaknut.dfs.exceptions.DiskFullError", ExitCode.CANT_CREATE),
    ("oaknut.dfs.exceptions.FileLocked", ExitCode.NO_PERM),
    ("oaknut.dfs.exceptions.InvalidFormatError", ExitCode.DATA_ERR),
    # --- ADFS ---
    ("oaknut.adfs.exceptions.ADFSDirectoryFullError", ExitCode.CANT_CREATE),
    ("oaknut.adfs.exceptions.ADFSDirectoryError", ExitCode.DATA_ERR),
    ("oaknut.adfs.exceptions.ADFSDiscFullError", ExitCode.CANT_CREATE),
    ("oaknut.adfs.exceptions.ADFSMapError", ExitCode.DATA_ERR),
    ("oaknut.adfs.exceptions.ADFSEntryExistsError", ExitCode.CANT_CREATE),
    ("oaknut.adfs.exceptions.ADFSDirectoryNotEmptyError", ExitCode.CANT_CREATE),
    ("oaknut.adfs.exceptions.ADFSPathError", ExitCode.OS_FILE),
    ("oaknut.adfs.exceptions.ADFSFileLockedError", ExitCode.NO_PERM),
    # --- AFS ---
    ("oaknut.afs.exceptions.AFSDirectoryFullError", ExitCode.CANT_CREATE),
    ("oaknut.afs.exceptions.AFSDirectoryEntryExistsError", ExitCode.CANT_CREATE),
    ("oaknut.afs.exceptions.AFSDirectoryEntryNotFoundError", ExitCode.OS_FILE),
    ("oaknut.afs.exceptions.AFSDirectoryNotEmptyError", ExitCode.CANT_CREATE),
    ("oaknut.afs.exceptions.AFSPathError", ExitCode.OS_FILE),
    ("oaknut.afs.exceptions.AFSAccessDeniedError", ExitCode.NO_PERM),
    ("oaknut.afs.exceptions.AFSFileLockedError", ExitCode.NO_PERM),
    ("oaknut.afs.exceptions.AFSInsufficientSpaceError", ExitCode.CANT_CREATE),
    ("oaknut.afs.exceptions.AFSQuotaExceededError", ExitCode.CANT_CREATE),
    ("oaknut.afs.exceptions.AFSFormatError", ExitCode.DATA_ERR),
    ("oaknut.afs.exceptions.AFSInitSpecError", ExitCode.USAGE),
    ("oaknut.afs.exceptions.AFSRepartitionError", ExitCode.DATA_ERR),
    ("oaknut.afs.exceptions.AFSMergeConflictError", ExitCode.DATA_ERR),
    ("oaknut.afs.exceptions.AFSHostImportError", ExitCode.IO_ERR),
    ("oaknut.afs.exceptions.AFSUserNotFoundError", ExitCode.OS_FILE),
    ("oaknut.afs.exceptions.AFSUserExistsError", ExitCode.CANT_CREATE),
)


def _resolve_class(dotted: str) -> type | None:
    """Import the module and return the class, or ``None`` if absent.

    Returns ``None`` rather than raising so the mapping stays resilient
    when a class is renamed or removed in a library package; the only
    consequence is that the fallback :data:`ExitCode.SOFTWARE` will be
    used.
    """
    module_name, _, class_name = dotted.rpartition(".")
    try:
        module = __import__(module_name, fromlist=[class_name])
    except ImportError:
        return None
    return getattr(module, class_name, None)


_RESOLVED_EXIT_CODES: dict[type, ExitCode] | None = None


def _exit_code_table() -> dict[type, ExitCode]:
    global _RESOLVED_EXIT_CODES
    if _RESOLVED_EXIT_CODES is None:
        table: dict[type, ExitCode] = {}
        for dotted, code in _CLASS_PATH_EXIT_CODES:
            cls = _resolve_class(dotted)
            if cls is not None:
                table[cls] = code
        _RESOLVED_EXIT_CODES = table
    return _RESOLVED_EXIT_CODES


def exit_code_for(exc: BaseException) -> ExitCode:
    """Return the :class:`ExitCode` for an ``FSError`` instance.

    Walks the MRO from most-specific to least-specific so subclasses
    inherit their parent's code automatically. Falls back to
    :data:`ExitCode.SOFTWARE` if no ancestor is in the table.
    """
    table = _exit_code_table()
    for ancestor in type(exc).__mro__:
        code = table.get(ancestor)
        if code is not None:
            return code
    return ExitCode.SOFTWARE


# ---------------------------------------------------------------------------
# FSClickException -- a ClickException with a settable exit code.
# ---------------------------------------------------------------------------


class FSClickException(click.ClickException):
    """``click.ClickException`` with a per-category :class:`ExitCode`.

    Click's stock ``ClickException`` hard-codes ``exit_code = 1``; we
    override it instance-by-instance so each FSError category surfaces
    its own stable code. The constructor accepts the ``ExitCode`` enum
    member (or any int) and stores its integer value where Click
    expects it.
    """

    def __init__(self, message: str, exit_code: ExitCode | int) -> None:
        super().__init__(message)
        self.exit_code = int(exit_code)


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

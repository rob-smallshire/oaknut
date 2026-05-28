"""Exceptions for the filesystem contract."""

from __future__ import annotations

from oaknut.exception import DataError, ExitCode
from oaknut.extension import ExtensionError


class FilesystemError(DataError):
    """Base for errors raised by the oaknut filesystem layer."""


class GeometryError(FilesystemError):
    """A geometry specification could not be parsed, or is invalid."""


class ReadOnlyFilesystemError(FilesystemError):
    """A mutating operation was attempted on a read-only mount.

    Raised by a :class:`~oaknut.filesystem.Mount` whose backing
    filesystem cannot be written (a ZIP archive, say). Carries the
    "operation not permitted" exit code so the CLI reports a clear
    refusal rather than a generic data error.
    """

    _exit_code = ExitCode.NO_PERM


class FilesystemExtensionError(ExtensionError):
    """A filesystem extension could not be discovered or loaded.

    A missing or mis-registered filesystem plug-in is an environment
    problem, so this inherits the configuration exit code via
    :class:`~oaknut.extension.ExtensionError`.
    """

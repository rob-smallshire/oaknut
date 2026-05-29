"""Exceptions for the filesystem contract."""

from __future__ import annotations

from oaknut.exception import DataError, ExitCode
from oaknut.extension import ExtensionError


class FilesystemError(DataError):
    """Base for errors raised by the oaknut filesystem layer."""


class GeometryError(FilesystemError):
    """A geometry specification could not be parsed, or is invalid."""


class NoSuchVolumeError(FilesystemError):
    """A volume designation addresses a volume the image does not have.

    Raised when a path names a volume (a DFS drive, ``:2``) that the
    geometry has no surface for — e.g. drive ``:2`` on a single-sided
    image. The addressed thing is absent, so this carries the
    "path not found" exit code. The message quotes the
    *designation*, never the internal surface index.
    """

    _exit_code = ExitCode.OS_FILE


class VolumeNotFormattedError(FilesystemError):
    """An addressed volume's surface carries no valid filesystem.

    The surface exists in the geometry but holds no valid structure —
    e.g. the second side implied for a length-ambiguous image turns out
    to be unformatted, so the image was single-sided after all. The data
    on that surface is not what the filesystem requires, so this carries
    the invalid-data exit code (the :class:`FilesystemError` default).
    """


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

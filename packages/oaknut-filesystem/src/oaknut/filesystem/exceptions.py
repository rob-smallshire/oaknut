"""Exceptions for the filesystem contract."""

from __future__ import annotations

from oaknut.exception import DataError
from oaknut.extension import ExtensionError


class FilesystemError(DataError):
    """Base for errors raised by the oaknut filesystem layer."""


class GeometryError(FilesystemError):
    """A geometry specification could not be parsed, or is invalid."""


class FilesystemExtensionError(ExtensionError):
    """A filesystem extension could not be discovered or loaded.

    A missing or mis-registered filesystem plug-in is an environment
    problem, so this inherits the configuration exit code via
    :class:`~oaknut.extension.ExtensionError`.
    """

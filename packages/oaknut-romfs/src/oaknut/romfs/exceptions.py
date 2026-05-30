"""Exception hierarchy for oaknut.romfs.

All ROMFS-specific exceptions derive from :class:`ROMFSError`, which in
turn derives from the shared :class:`~oaknut.file.exceptions.FSError` base
(a ``DataError``). The CLI boundary reads an exception's ``exit_code`` to
decide its exit status, so each subclass pins a specific :class:`ExitCode`.

Hierarchy::

    FSError (oaknut.file.exceptions, a DataError)
    └── ROMFSError
        ├── NotAROMFSError      (ExitCode.DATA_ERR)
        ├── CRCError            (ExitCode.DATA_ERR)
        ├── TruncatedROMError   (ExitCode.DATA_ERR)
        └── ROMFullError        (ExitCode.CANT_CREATE)
"""

from __future__ import annotations

from exit_codes import ExitCode
from oaknut.file.exceptions import FSError


class ROMFSError(FSError):
    """Base exception for all ROMFS errors."""


class NotAROMFSError(ROMFSError):
    """The image is not a recognisable ROMFS paged ROM."""

    _exit_code = ExitCode.DATA_ERR


class CRCError(ROMFSError):
    """A stored header or data CRC does not match the computed value."""

    _exit_code = ExitCode.DATA_ERR


class TruncatedROMError(ROMFSError):
    """The ROM ends in the middle of a block header or its data."""

    _exit_code = ExitCode.DATA_ERR


class ROMFullError(ROMFSError):
    """The files no longer fit within the ROM's capacity."""

    _exit_code = ExitCode.CANT_CREATE

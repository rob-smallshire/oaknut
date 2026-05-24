"""Exception hierarchy for oaknut.dfs library.

All DFS-specific exceptions derive from DFSError, which in turn
derives from the shared ``FSError`` base defined in oaknut.file.
ADFS exception subclasses live in oaknut.adfs.exceptions.

Each subclass below pins a more specific :class:`ExitCode` than the
``ExitCode.DATA_ERR`` it inherits from ``DataError``. The CLI
boundary just reads the exception's :attr:`exit_code` to decide its
exit status — no per-class mapping table is needed in the CLI side.

Hierarchy::

    FSError (oaknut.file.exceptions, a DataError)
    └── DFSError
        ├── CatalogError
        │   ├── CatalogReadError      (ExitCode.DATA_ERR)
        │   ├── CatalogFullError      (ExitCode.CANT_CREATE)
        │   └── FileExistsError       (ExitCode.CANT_CREATE)
        ├── DiscFullError             (ExitCode.CANT_CREATE)
        ├── FileLocked                (ExitCode.NO_PERM)
        └── InvalidFormatError        (ExitCode.DATA_ERR)
"""

from exit_codes import ExitCode
from oaknut.file.exceptions import FSError


class DFSError(FSError):
    """Base exception for all DFS errors."""


class CatalogError(DFSError):
    """Base exception for catalog-related errors.

    Raised when operations on the disc catalog fail.
    """


class CatalogReadError(CatalogError):
    """Failed to read or parse catalog structure.

    Raised when the catalog data is corrupted, invalid, or cannot be decoded.
    This typically indicates disc corruption or an unsupported format variant.
    """

    _exit_code = ExitCode.DATA_ERR


class CatalogFullError(CatalogError):
    """Catalog is full and cannot accept more files.

    Raised when attempting to add a file to a catalog that has reached
    its maximum capacity (31 files for standard Acorn DFS).
    """

    _exit_code = ExitCode.CANT_CREATE


class FileExistsError(CatalogError):
    """File already exists in catalog.

    Raised when attempting to add a file with a name that already exists.
    Note: This shadows the builtin FileExistsError, providing DFS-specific context.
    """

    _exit_code = ExitCode.CANT_CREATE


class DiscFullError(DFSError):
    """Insufficient free space on disc.

    Raised when attempting to save a file but there aren't enough
    free sectors available.
    """

    _exit_code = ExitCode.CANT_CREATE


class FileLocked(DFSError):
    """Operation not permitted on locked file.

    Raised when attempting to delete, rename, or modify a file
    that has the locked attribute set.
    """

    _exit_code = ExitCode.NO_PERM


class InvalidFormatError(DFSError):
    """Disc image format is invalid or unrecognised.

    Raised when the disc image doesn't match expected DFS format,
    has invalid size, or contains malformed data structures.
    """

    _exit_code = ExitCode.DATA_ERR


class DFSFormatError(DFSError):
    """The caller did not provide enough information to pick a DFS format.

    Raised by :meth:`DFS.create_file` when the filename extension
    does not uniquely identify a format and no explicit
    :class:`DiscFormat` argument was supplied.
    """

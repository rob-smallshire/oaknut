"""Exception hierarchy for oaknut.dfs library.

All DFS-specific exceptions derive from DFSError, which in turn
derives from the shared ``FSError`` base defined in oaknut.file.
ADFS exception subclasses live in oaknut.adfs.exceptions.

Hierarchy::

    FSError (oaknut.file.exceptions)
    └── DFSError
        ├── CatalogError
        │   ├── CatalogReadError
        │   ├── CatalogFullError
        │   └── FileExistsError
        ├── DiskFullError
        ├── FileLocked
        └── InvalidFormatError
"""

from oaknut.file.exceptions import FSError


class DFSError(FSError):
    """Base exception for all DFS errors."""

    pass


class CatalogError(DFSError):
    """Base exception for catalog-related errors.

    Raised when operations on the disc catalog fail.
    """

    pass


class CatalogReadError(CatalogError):
    """Failed to read or parse catalog structure.

    Raised when the catalog data is corrupted, invalid, or cannot be decoded.
    This typically indicates disc corruption or an unsupported format variant.
    """

    pass


class CatalogFullError(CatalogError):
    """Catalog is full and cannot accept more files.

    Raised when attempting to add a file to a catalog that has reached
    its maximum capacity (31 files for standard Acorn DFS).
    """

    pass


class FileExistsError(CatalogError):
    """File already exists in catalog.

    Raised when attempting to add a file with a name that already exists.
    Note: This shadows the builtin FileExistsError, providing DFS-specific context.
    """

    pass


class DiskFullError(DFSError):
    """Insufficient free space on disc.

    Raised when attempting to save a file but there aren't enough
    free sectors available.
    """

    pass


class FileLocked(DFSError):
    """Operation not permitted on locked file.

    Raised when attempting to delete, rename, or modify a file
    that has the locked attribute set.
    """

    pass


class InvalidFormatError(DFSError):
    """Disc image format is invalid or unrecognised.

    Raised when the disc image doesn't match expected DFS format,
    has invalid size, or contains malformed data structures.
    """

    pass

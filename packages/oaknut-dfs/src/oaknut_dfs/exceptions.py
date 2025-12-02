"""Exception hierarchy for oaknut_dfs library.

This module defines custom exceptions for domain-specific errors in DFS operations.
Using custom exceptions provides:
1. Clear error categories for library users
2. Ability to catch broad (DFSError) or specific (CatalogFullError) exceptions
3. Better API documentation through explicit exception types
4. More precise error handling than generic ValueError or RuntimeError
"""


class DFSError(Exception):
    """Base exception for all oaknut_dfs errors.

    All custom exceptions in this library derive from DFSError,
    allowing callers to catch all library-specific errors with a single handler.
    """
    pass


# Catalog-related exceptions

class CatalogError(DFSError):
    """Base exception for catalog-related errors.

    Raised when operations on the disk catalog fail.
    """
    pass


class CatalogReadError(CatalogError):
    """Failed to read or parse catalog structure.

    Raised when the catalog data is corrupted, invalid, or cannot be decoded.
    This typically indicates disk corruption or an unsupported format variant.
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


# Disk space and file operation exceptions

class DiskFullError(DFSError):
    """Insufficient free space on disk.

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


# Format and validation exceptions

class InvalidFormatError(DFSError):
    """Disk image format is invalid or unrecognized.

    Raised when the disk image doesn't match expected DFS format,
    has invalid size, or contains malformed data structures.
    """
    pass

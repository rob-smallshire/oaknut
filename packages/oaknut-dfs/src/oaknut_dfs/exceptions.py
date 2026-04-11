"""Exception hierarchy for oaknut_dfs library.

All exceptions derive from FSError, the common root for both DFS and ADFS
filesystem errors. This allows callers to catch all library errors with a
single handler, or to catch DFS-specific or ADFS-specific errors separately.

Hierarchy:

    FSError
    ├── DFSError
    │   ├── CatalogError
    │   │   ├── CatalogReadError
    │   │   ├── CatalogFullError
    │   │   └── FileExistsError
    │   ├── DiskFullError
    │   ├── FileLocked
    │   └── InvalidFormatError
    └── ADFSError
        ├── ADFSDirectoryError
        │   └── ADFSDirectoryFullError
        ├── ADFSMapError
        │   └── ADFSDiscFullError
        ├── ADFSPathError
        └── ADFSFileLockedError
"""


class FSError(Exception):
    """Base exception for all oaknut_dfs filesystem errors.

    Catches both DFS and ADFS errors with a single handler.
    """
    pass


# --- DFS exceptions ---


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


# --- ADFS exceptions ---


class ADFSError(FSError):
    """Base exception for all ADFS errors."""
    pass


class ADFSDirectoryError(ADFSError):
    """ADFS directory structure error.

    Raised when a directory block has an invalid checksum,
    unrecognised magic bytes, or other structural problems.
    """
    pass


class ADFSDirectoryFullError(ADFSDirectoryError):
    """ADFS directory is full and cannot accept more entries.

    Raised when attempting to add an entry to a directory that has
    reached its maximum capacity (47 entries for old-format directories).
    """
    pass


class ADFSMapError(ADFSError):
    """ADFS free space map error.

    Raised when the free space map has an invalid checksum
    or inconsistent data.
    """
    pass


class ADFSDiscFullError(ADFSMapError):
    """Insufficient free space on ADFS disc.

    Raised when attempting to allocate sectors but no free space
    region is large enough.
    """
    pass


class ADFSPathError(ADFSError):
    """ADFS path error.

    Raised for invalid paths, paths that do not exist,
    or path components with forbidden characters.
    """
    pass


class ADFSFileLockedError(ADFSError):
    """Operation not permitted on locked ADFS file.

    Raised when attempting to delete, rename, or modify a file
    that has the locked attribute set.
    """
    pass

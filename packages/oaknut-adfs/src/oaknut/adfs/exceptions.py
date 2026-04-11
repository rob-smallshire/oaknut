"""Exception hierarchy for oaknut.adfs.

Every ADFS-specific error derives from ``ADFSError``, which in turn
derives from the shared ``FSError`` base in oaknut.file. Callers
that want to catch any filesystem error catch ``FSError``; callers
that care specifically about ADFS catch ``ADFSError``.

Hierarchy::

    FSError (oaknut.file.exceptions)
    └── ADFSError
        ├── ADFSDirectoryError
        │   └── ADFSDirectoryFullError
        ├── ADFSMapError
        │   └── ADFSDiscFullError
        ├── ADFSPathError
        └── ADFSFileLockedError
"""

from oaknut.file.exceptions import FSError


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

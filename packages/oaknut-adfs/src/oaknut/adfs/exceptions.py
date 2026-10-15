"""Exception hierarchy for oaknut.adfs.

Every ADFS-specific error derives from ``ADFSError``, which in turn
derives from the shared ``FSError`` base in oaknut.file. Callers
that want to catch any filesystem error catch ``FSError``; callers
that care specifically about ADFS catch ``ADFSError``.

Each subclass below pins a more specific :class:`ExitCode` than the
``ExitCode.DATA_ERR`` it inherits from ``DataError``.

Hierarchy::

    FSError (oaknut.file.exceptions, a DataError)
    └── ADFSError
        ├── ADFSBeyondImageError
        ├── ADFSDirectoryError
        │   └── ADFSDirectoryFullError    (ExitCode.CANT_CREATE)
        ├── ADFSMapError
        │   └── ADFSDiscFullError         (ExitCode.CANT_CREATE)
        ├── ADFSPathError                 (ExitCode.OS_FILE)
        │   ├── ADFSEntryExistsError      (ExitCode.CANT_CREATE)
        │   └── ADFSDirectoryNotEmptyError(ExitCode.CANT_CREATE)
        └── ADFSFileLockedError           (ExitCode.NO_PERM)

``ADFSEntryExistsError`` and ``ADFSDirectoryNotEmptyError`` are
subclasses of ``ADFSPathError`` for backwards compatibility -- callers
that previously caught ``ADFSPathError`` for "already exists" or "not
empty" continue to do so. Their own ``_exit_code`` overrides the
parent's ``OS_FILE`` so the CLI distinguishes them from
"not found".
"""

from exit_codes import ExitCode
from oaknut.file.exceptions import FSError


class ADFSError(FSError):
    """Base exception for all ADFS errors."""


class ADFSFormatError(ADFSError):
    """The caller did not provide enough information to pick an ADFS format.

    Raised by :meth:`ADFS.create_file` when the filename extension
    does not uniquely identify a format and no explicit
    :class:`ADFSFormat` argument was supplied.
    """


class ADFSBeyondImageError(ADFSError):
    """An object lies wholly or partly past the end of the disc image.

    Raised when a directory or a file's data is read from sectors the
    image does not hold -- typically an image captured or trimmed short of
    the disc its free-space map describes.
    """

    def __init__(self, what: str, start_sector: int, num_sectors: int, image_sectors: int):
        self.start_sector = start_sector
        self.num_sectors = num_sectors
        self.image_sectors = image_sectors
        end_sector = start_sector + num_sectors - 1
        if start_sector >= image_sectors:
            message = (
                f"{what} at sector {start_sector} lies past the end of the image "
                f"({image_sectors} sectors)"
            )
        else:
            message = (
                f"{what} (sectors {start_sector}-{end_sector}) runs past the end of "
                f"the image ({image_sectors} sectors)"
            )
        super().__init__(message)


class ADFSDirectoryError(ADFSError):
    """ADFS directory structure error.

    Raised when a directory block has an invalid checksum,
    unrecognised magic bytes, or other structural problems.
    """


class ADFSDirectoryFullError(ADFSDirectoryError):
    """ADFS directory is full and cannot accept more entries.

    Raised when attempting to add an entry to a directory that has
    reached its maximum capacity (47 entries for old-format directories).
    """

    _exit_code = ExitCode.CANT_CREATE


class ADFSMapError(ADFSError):
    """ADFS free space map error.

    Raised when the free space map has an invalid checksum
    or inconsistent data.
    """


class ADFSDiscFullError(ADFSMapError):
    """Insufficient free space on ADFS disc.

    Raised when attempting to allocate sectors but no free space
    region is large enough.
    """

    _exit_code = ExitCode.CANT_CREATE


class ADFSPathError(ADFSError):
    """ADFS path error.

    Raised for invalid paths, paths that do not exist,
    or path components with forbidden characters.
    """

    _exit_code = ExitCode.OS_FILE


class ADFSEntryExistsError(ADFSPathError):
    """A directory entry with the requested name already exists.

    Raised by :meth:`ADFS._mkdir` and :meth:`ADFS._rename` when the
    destination name collides with an existing entry. Subclass of
    :class:`ADFSPathError` for backwards compatibility -- callers that
    previously matched on the broader class continue to work.
    """

    _exit_code = ExitCode.CANT_CREATE


class ADFSDirectoryNotEmptyError(ADFSPathError):
    """Cannot remove a directory that still has entries.

    Raised by :meth:`ADFS._rmdir` when the target directory has at
    least one entry. Subclass of :class:`ADFSPathError` for backwards
    compatibility.
    """

    _exit_code = ExitCode.CANT_CREATE


class ADFSFileLockedError(ADFSError):
    """Operation not permitted on locked ADFS file.

    Raised when attempting to delete, rename, or modify a file
    that has the locked attribute set.
    """

    _exit_code = ExitCode.NO_PERM


class ADFSValidationError(ADFSError):
    """A problem detected by disc-image validation.

    :meth:`ADFS.validate` returns a list of these (empty when the
    image is clean) rather than raising — callers typically want to
    enumerate every defect, not abort on the first one. Each instance
    carries a human-readable description as its message; the CLI
    renders these via the standard error pipeline.
    """

    _exit_code = ExitCode.DATA_ERR

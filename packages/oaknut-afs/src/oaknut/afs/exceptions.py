"""Exception hierarchy for oaknut.afs.

Every AFS-specific error derives from ``AFSError``, which in turn
derives from the shared ``FSError`` base in ``oaknut.file``. Callers
who want to catch any filesystem error catch ``FSError``; callers who
care specifically about AFS catch ``AFSError``.

Where the Level 3 File Server reports a numeric FS error code (see
``docs/afs-onwire.md`` §FS error codes), the exception carries it on
``err.fs_error_code`` for symmetry with the server's own reporting.

Hierarchy::

    FSError  (oaknut.file.exceptions)
    └── AFSError
        ├── AFSFormatError
        │   ├── AFSBrokenDirectoryError   (fs_error_code = 0x42)
        │   ├── AFSBrokenMapError
        │   └── AFSInfoSectorError
        ├── AFSPathError
        ├── AFSAccessDeniedError          (fs_error_code = 0xBD)
        ├── AFSFileLockedError            (fs_error_code = 0xC3)
        ├── AFSInsufficientSpaceError     (fs_error_code = 0xC6)
        ├── AFSQuotaExceededError         (fs_error_code = 0x5C)
        ├── AFSRepartitionError
        │   ├── AFSNewMapNotSupportedError
        │   ├── AFSDiscNotCompactedError
        │   ├── AFSAlreadyPartitionedError
        │   └── AFSInsufficientADFSSpaceError
        ├── AFSMergeConflictError
        └── AFSHostImportError
"""

from __future__ import annotations

from oaknut.file.exceptions import FSError


class AFSError(FSError):
    """Base exception for all AFS errors."""

    fs_error_code: int | None = None


# ---------------------------------------------------------------------------
# Format errors — raised when on-disc bytes do not match the AFS format.
# ---------------------------------------------------------------------------


class AFSFormatError(AFSError):
    """Malformed on-disc AFS structure."""


class AFSBrokenDirectoryError(AFSFormatError):
    """Master-sequence-number mismatch on a directory object.

    The leading and trailing master-sequence bytes do not agree, which
    the file server reports as FS error &42 ("Broken Directory"). This
    typically means a write to the directory was interrupted.
    """

    fs_error_code = 0x42


class AFSBrokenMapError(AFSFormatError):
    """Invalid ``JesMap`` magic or sequence-number mismatch."""


class AFSInfoSectorError(AFSFormatError):
    """Invalid ``AFS0`` magic or redundancy mismatch between info sectors."""


# ---------------------------------------------------------------------------
# Access / permission errors.
# ---------------------------------------------------------------------------


class AFSPathError(AFSError):
    """Path syntax error or non-existent object.

    Covers invalid file titles, bad separators, paths that traverse
    through something that isn't a directory, and ``$.foo`` where
    ``foo`` does not exist.
    """


class AFSAccessDeniedError(AFSError):
    """Acting user lacks permission for the requested operation."""

    fs_error_code = 0xBD  # DRERRE — insufficient access


class AFSFileLockedError(AFSError):
    """Operation refused because the object's ``L`` bit is set."""

    fs_error_code = 0xC3  # DRERRG — dir entry locked


# ---------------------------------------------------------------------------
# Space / quota errors.
# ---------------------------------------------------------------------------


class AFSInsufficientSpaceError(AFSError):
    """The allocator cannot satisfy a request from the free space pool."""

    fs_error_code = 0xC6  # MPERRB — disc space exhausted


class AFSQuotaExceededError(AFSError):
    """The acting user does not have enough quota for this operation."""

    fs_error_code = 0x5C  # MPERRN — insufficient user free space


# ---------------------------------------------------------------------------
# Repartitioning errors.
# ---------------------------------------------------------------------------


class AFSRepartitionError(AFSError):
    """Base for repartitioning failures."""


class AFSNewMapNotSupportedError(AFSRepartitionError):
    """Refused: the ADFS disc uses the new-map format.

    v1 of ``oaknut-afs`` supports old-map (S/M/L/D-style) ADFS hosts
    only. The new-map formats (E/E+/F/F+) use the reserved bytes
    differently and do not carry AFS pointers.
    """


class AFSDiscNotCompactedError(AFSRepartitionError):
    """Refused: the ADFS free list is fragmented and compaction is disabled.

    Raised only when ``partition.plan(..., compact_adfs=False)``. Pass
    ``compact_adfs=True`` (the default) to have the repartitioner run
    ``ADFS.compact()`` first.
    """


class AFSAlreadyPartitionedError(AFSRepartitionError):
    """Refused: the disc already contains AFS pointers at &F6/&1F6."""


class AFSInsufficientADFSSpaceError(AFSRepartitionError):
    """Refused: the requested AFS size would leave too little space for ADFS."""


# ---------------------------------------------------------------------------
# Merge / import errors.
# ---------------------------------------------------------------------------


class AFSMergeConflictError(AFSError):
    """A target name already exists and the merge policy is ``"error"``."""


class AFSHostImportError(AFSError):
    """``import_host_tree`` failed to read or translate a host-side file."""

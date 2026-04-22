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
        ├── AFSDirectoryFullError         (no growth room — phase 10 will auto-grow)
        ├── AFSDirectoryEntryExistsError
        ├── AFSDirectoryEntryNotFoundError
        ├── AFSDirectoryNotEmptyError
        ├── AFSRepartitionError
        │   ├── AFSNewMapNotSupportedError
        │   ├── AFSDiscNotCompactedError
        │   ├── AFSAlreadyPartitionedError
        │   └── AFSInsufficientADFSSpaceError
        ├── AFSInitSpecError
        │   ├── AFSDiscNameError
        │   ├── AFSUserNameError
        │   ├── AFSPasswordError
        │   └── AFSQuotaError
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
# Directory mutation errors (phase 9+).
# ---------------------------------------------------------------------------


class AFSDirectoryFullError(AFSError):
    """Cannot insert into a directory whose free list is empty.

    The Level 3 File Server handles this by growing the directory
    automatically via ``CHZSZE`` (Uade0E:1198). The oaknut-afs write
    path currently raises this error when growth would be required
    — phase 10 will add automatic growth, matching the ROM.
    """


class AFSDirectoryEntryExistsError(AFSError):
    """An entry with the same name already exists in the directory."""


class AFSDirectoryEntryNotFoundError(AFSError):
    """No entry with the requested name exists in the directory.

    Corresponds to the server's ``DRERRC`` error code returned by
    ``FNDTEX`` at ``Uade0D:249`` when the walk reaches the end of
    the in-use list without a match.
    """


class AFSDirectoryNotEmptyError(AFSError):
    """Cannot remove a directory that still has entries.

    Raised by ``rmdir`` / ``unlink`` on a non-empty sub-directory,
    matching ``DELCHK`` at ``Uade0D:1218+`` (``DRERRJ``).
    """


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
# Init-spec validation errors — raised at InitSpec/UserSpec construction
# time before any disc mutation (see issue #3).
# ---------------------------------------------------------------------------


class AFSInitSpecError(AFSError):
    """Base for InitSpec / UserSpec validation failures."""


class AFSDiscNameError(AFSInitSpecError):
    """The proposed AFS disc name is empty, too long, or contains
    non-printable / space characters (printable ASCII only, 1..16 chars).
    """


class AFSUserNameError(AFSInitSpecError):
    """A user name is empty, not ASCII, or exceeds 20 characters."""


class AFSPasswordError(AFSInitSpecError):
    """A password is not ASCII or exceeds 6 characters."""


class AFSQuotaError(AFSInitSpecError):
    """A quota (per-user or default) is outside 0..0xFFFFFFFF."""


# ---------------------------------------------------------------------------
# Merge / import errors.
# ---------------------------------------------------------------------------


class AFSMergeConflictError(AFSError):
    """A target name already exists and the merge policy is ``"error"``."""


class AFSHostImportError(AFSError):
    """``import_host_tree`` failed to read or translate a host-side file."""

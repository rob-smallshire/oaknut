"""Acorn Level 3 File Server (AFS) filesystem support.

The Level 3 File Server's private on-disc filesystem, identified by
the ``AFS0`` magic in its info sectors. An AFS region occupies the
tail cylinders of an old-map ADFS hard-disc image; the ADFS partition
at the front of the disc coexists with it.

The ``A`` in ``AFS0`` most likely stands for *Acorn File Server*,
though no primary source spells it out — the ``0`` is a format version.

The full public API — read, write, merge, initialise, and CLI — is
implemented. See ``docs/afs-implementation-plan.md`` for the design
and ``docs/afs-onwire.md`` for the on-disc format specification.
"""

__version__ = "10.4.0"

from oaknut.afs.access import AFSAccess
from oaknut.afs.afs import AFS, AFSNotPresentError
from oaknut.afs.allocator import Allocator
from oaknut.afs.exceptions import (
    AFSAccessDeniedError,
    AFSAlreadyPartitionedError,
    AFSBrokenDirectoryError,
    AFSBrokenMapError,
    AFSDirectoryEntryExistsError,
    AFSDirectoryEntryNotFoundError,
    AFSDirectoryFullError,
    AFSDirectoryNotEmptyError,
    AFSDiscNameError,
    AFSDiscNotCompactedError,
    AFSError,
    AFSFileLockedError,
    AFSFormatError,
    AFSHostImportError,
    AFSInfoSectorError,
    AFSInitSpecError,
    AFSInsufficientADFSSpaceError,
    AFSInsufficientSpaceError,
    AFSMergeConflictError,
    AFSNewMapNotSupportedError,
    AFSPasswordError,
    AFSPathError,
    AFSQuotaError,
    AFSQuotaExceededError,
    AFSRepartitionError,
    AFSUserNameError,
)
from oaknut.afs.host_import import import_host_tree
from oaknut.afs.libraries import SHIPPED_LIBRARIES, emplace_library
from oaknut.afs.merge import merge
from oaknut.afs.passwords import PasswordsFile, UserRecord
from oaknut.afs.path import AFSPath
from oaknut.afs.types import (
    AfsDate,
    Cylinder,
    Geometry,
    Sector,
    SystemInternalName,
)

__all__ = [
    "AFS",
    "AFSAccess",
    "AFSNotPresentError",
    "AFSPath",
    "Allocator",
    "SHIPPED_LIBRARIES",
    "emplace_library",
    "PasswordsFile",
    "UserRecord",
    "import_host_tree",
    "merge",
    "AFSAccessDeniedError",
    "AFSAlreadyPartitionedError",
    "AFSBrokenDirectoryError",
    "AFSBrokenMapError",
    "AFSDirectoryEntryExistsError",
    "AFSDirectoryEntryNotFoundError",
    "AFSDirectoryFullError",
    "AFSDirectoryNotEmptyError",
    "AFSDiscNameError",
    "AFSDiscNotCompactedError",
    "AFSError",
    "AFSFileLockedError",
    "AFSFormatError",
    "AFSHostImportError",
    "AFSInfoSectorError",
    "AFSInitSpecError",
    "AFSInsufficientADFSSpaceError",
    "AFSInsufficientSpaceError",
    "AFSMergeConflictError",
    "AFSNewMapNotSupportedError",
    "AFSPasswordError",
    "AFSPathError",
    "AFSQuotaError",
    "AFSQuotaExceededError",
    "AFSRepartitionError",
    "AFSUserNameError",
    "AfsDate",
    "Cylinder",
    "Geometry",
    "Sector",
    "SystemInternalName",
]

``oaknut.afs``
==============

The Acorn Level 3 File Server's private on-disc filesystem, identified
by the ``AFS0`` magic. An AFS region occupies the tail cylinders of an
old-map ADFS hard-disc image, coexisting with the ADFS partition at the
front of the same disc, so an AFS handle is opened through its host
:class:`~oaknut.adfs.ADFS` (see :doc:`adfs`).

Every name documented here is importable directly from ``oaknut.afs``.


The filesystem
--------------

.. autoclass:: oaknut.afs.AFS
   :members:

.. autoclass:: oaknut.afs.AFSPath
   :members:

.. autoclass:: oaknut.afs.AFSAccess
   :members:


Initialisation and partitioning
-------------------------------

Partitioning an ADFS hard disc for AFS and initialising an empty
filesystem — the library analogue of ``WFSINIT``. The spec objects
describe the desired partition size and initial user accounts.

.. autofunction:: oaknut.afs.initialise

.. autoclass:: oaknut.afs.InitSpec
   :members:

.. autoclass:: oaknut.afs.UserSpec
   :members:

.. autoclass:: oaknut.afs.AFSSizeSpec
   :members:

.. autoclass:: oaknut.afs.RepartitionPlan
   :members:

.. autodata:: oaknut.afs.BUILTIN_ACCOUNT_NAMES


Bulk operations
---------------

Composing files into an AFS region in bulk: merging another tree,
importing a host directory tree, and emplacing one of the shipped
library images.

.. autofunction:: oaknut.afs.merge

.. autofunction:: oaknut.afs.import_host_tree

.. autofunction:: oaknut.afs.emplace_library

.. autodata:: oaknut.afs.SHIPPED_LIBRARIES


Passwords
---------

The file server's ``Passwords`` account file: the per-user records and
the file that holds them.

.. autoclass:: oaknut.afs.PasswordsFile
   :members:

.. autoclass:: oaknut.afs.UserRecord
   :members:


Free-space allocation
---------------------

.. autoclass:: oaknut.afs.Allocator
   :members:


Disc geometry and types
------------------------

The geometry of the host hard disc and the small domain types used
throughout the on-disc structures.

.. autoclass:: oaknut.afs.Geometry
   :members:

.. autoclass:: oaknut.afs.AfsDate
   :members:

.. autodata:: oaknut.afs.Cylinder

.. autodata:: oaknut.afs.Sector

.. autodata:: oaknut.afs.SystemInternalName


Errors
------

The AFS exception hierarchy. ``AFSError`` is the base; every other AFS
error inherits from it. The broader error model and the
``handled_errors`` boundary are covered in :doc:`/api/patterns/errors`.

.. autoexception:: oaknut.afs.AFSError

.. autoexception:: oaknut.afs.AFSNotPresentError

.. autoexception:: oaknut.afs.AFSAccessDeniedError

.. autoexception:: oaknut.afs.AFSAlreadyPartitionedError

.. autoexception:: oaknut.afs.AFSBrokenDirectoryError

.. autoexception:: oaknut.afs.AFSBrokenMapError

.. autoexception:: oaknut.afs.AFSDirectoryEntryExistsError

.. autoexception:: oaknut.afs.AFSDirectoryEntryNotFoundError

.. autoexception:: oaknut.afs.AFSDirectoryFullError

.. autoexception:: oaknut.afs.AFSDirectoryNotEmptyError

.. autoexception:: oaknut.afs.AFSDiscNameError

.. autoexception:: oaknut.afs.AFSDiscNotCompactedError

.. autoexception:: oaknut.afs.AFSFileLockedError

.. autoexception:: oaknut.afs.AFSFormatError

.. autoexception:: oaknut.afs.AFSHostImportError

.. autoexception:: oaknut.afs.AFSInfoSectorError

.. autoexception:: oaknut.afs.AFSInitSpecError

.. autoexception:: oaknut.afs.AFSInsufficientADFSSpaceError

.. autoexception:: oaknut.afs.AFSInsufficientSpaceError

.. autoexception:: oaknut.afs.AFSMergeConflictError

.. autoexception:: oaknut.afs.AFSNewMapNotSupportedError

.. autoexception:: oaknut.afs.AFSPasswordError

.. autoexception:: oaknut.afs.AFSPathError

.. autoexception:: oaknut.afs.AFSQuotaError

.. autoexception:: oaknut.afs.AFSQuotaExceededError

.. autoexception:: oaknut.afs.AFSRepartitionError

.. autoexception:: oaknut.afs.AFSUserNameError

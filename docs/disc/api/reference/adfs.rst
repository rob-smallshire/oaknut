``oaknut.adfs``
===============

ADFS — the Acorn Advanced Disc Filing System used by the BBC Master,
the Archimedes, and RISC OS machines. Unlike DFS it has a directory
hierarchy and a free-space map; it spans small (S), medium (M), and
large (L) floppy layouts as well as hard-disc images addressed through
an explicit geometry.

Every name documented here is importable directly from ``oaknut.adfs``.


The filesystem
--------------

.. autoclass:: oaknut.adfs.ADFS
   :members:

.. autoclass:: oaknut.adfs.ADFSPath
   :members:

.. autoclass:: oaknut.adfs.ADFSStat
   :members:


Disc formats
------------

An :class:`~oaknut.adfs.ADFSFormat` describes one ADFS layout. The three
standard floppy formats are provided as constants, and
:data:`~oaknut.adfs.IMAGE_FORMAT_BY_EXTENSION` maps a filename extension
to its format (``None`` for the extensions whose size must be measured
instead).

.. autoclass:: oaknut.adfs.ADFSFormat
   :members:

.. autodata:: oaknut.adfs.ADFS_S

.. autodata:: oaknut.adfs.ADFS_M

.. autodata:: oaknut.adfs.ADFS_L

.. autodata:: oaknut.adfs.ADFS_D

.. autodata:: oaknut.adfs.ADFS_E

.. autodata:: oaknut.adfs.ADFS_E_PLUS

.. autodata:: oaknut.adfs.ADFS_F

.. autodata:: oaknut.adfs.ADFS_F_PLUS

.. autodata:: oaknut.adfs.ADFS_G

.. autodata:: oaknut.adfs.ADFS_G_PLUS

.. autodata:: oaknut.adfs.IMAGE_FORMAT_BY_EXTENSION


Hard-disc geometry
------------------

Hard-disc images carry an explicit cylinders/heads/sectors geometry,
held in an :class:`~oaknut.adfs.ADFSGeometry` and persisted alongside
the image in a 22-byte ``.dsc`` sidecar, or a richer BeebSCSI/Pi1MHz
``.cfg`` extended-attributes file that also records sectors-per-track.

.. autoclass:: oaknut.adfs.ADFSGeometry
   :members:

.. autofunction:: oaknut.adfs.geometry_for_capacity

.. autofunction:: oaknut.adfs.write_dsc

.. autofunction:: oaknut.adfs.write_cfg


Access
------

An old-format ADFS directory entry carries owner read, write, execute
and locked bits and public read and write bits. The ADFS access convention maps
them to and from the :class:`~oaknut.file.Access` word (see
:class:`~oaknut.file.AccessConvention`).

.. autoclass:: oaknut.adfs.ADFSAccessConvention

.. autodata:: oaknut.adfs.ADFS_ACCESS

New and Big directories (the D, E, F, E+ and F+ formats) have no owner
execute, public execute or private bit, so they use their own convention;
:attr:`ADFS.access_convention <oaknut.adfs.ADFS.access_convention>`
gives the one for a disc.

.. autoclass:: oaknut.adfs.ADFSNewDirectoryAccessConvention

.. autodata:: oaknut.adfs.ADFS_NEW_DIRECTORY_ACCESS


See also
--------

ADFS access bits use the shared :class:`~oaknut.file.Access` enum, which
belongs to :doc:`oaknut.file <file>` (see also
:doc:`/api/patterns/metadata`); import it from there.

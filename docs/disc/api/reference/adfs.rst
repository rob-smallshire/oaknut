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
the image in a 22-byte ``.dsc`` sidecar.

.. autoclass:: oaknut.adfs.ADFSGeometry
   :members:

.. autofunction:: oaknut.adfs.geometry_for_capacity

.. autofunction:: oaknut.adfs.write_dsc


See also
--------

ADFS access bits use the shared :class:`~oaknut.file.Access` enum, which
belongs to :doc:`oaknut.file <file>` (see also
:doc:`/api/patterns/metadata`); import it from there.

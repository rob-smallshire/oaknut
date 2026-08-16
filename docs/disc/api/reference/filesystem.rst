``oaknut.filesystem``
=====================

The pluggable filesystem contract shared by the disc family. A
*filesystem* (Acorn DFS, Watford DFS, ADFS, AFS, …) is the unit of
extension, registered on the ``oaknut.filesystem`` entry-point axis.
Each :class:`~oaknut.filesystem.Filesystem` detects itself
(:meth:`~oaknut.filesystem.Filesystem.probe`), opens a region into a
:class:`~oaknut.filesystem.Mount` exposing a small core plus opt-in
capability protocols, and declares its physical
:class:`~oaknut.filesystem.Geometry` grammar.

Geometry (the physical byte→sector layout) and the filesystem (the
logical structure) are kept strictly apart.
:func:`~oaknut.filesystem.identify` runs the registered filesystems over
an image, ranks the candidates, and recurses into reserved regions to
build a per-partition :class:`~oaknut.filesystem.Identification` tree —
depending on, and importing, no concrete filesystem package.

Every name documented here is importable directly from
``oaknut.filesystem``.


The filesystem contract
-----------------------

.. autoclass:: oaknut.filesystem.Filesystem
   :members:

.. autodata:: oaknut.filesystem.FILESYSTEM_KIND

.. autodata:: oaknut.filesystem.FILESYSTEM_NAMESPACE


Capabilities
------------

A mount exposes a small required core (:class:`~oaknut.filesystem.Mount`)
plus whichever of these ``runtime_checkable`` protocols its filesystem
supports. Commands gate on the capability, never on the filesystem type,
so a filesystem that cannot do something simply does not implement the
protocol.

.. autoclass:: oaknut.filesystem.Mount
   :members:

.. autoclass:: oaknut.filesystem.Entry
   :members:

.. autoclass:: oaknut.filesystem.HierarchicalDirectories
   :members:

.. autoclass:: oaknut.filesystem.AcornMetadata
   :members:

.. autoclass:: oaknut.filesystem.Filetyped
   :members:

.. autoclass:: oaknut.filesystem.Datestamped
   :members:

.. autoclass:: oaknut.filesystem.Lens
   :members:

.. autoclass:: oaknut.filesystem.MetadataLensed
   :members:

.. autoclass:: oaknut.filesystem.Titled
   :members:

.. autoclass:: oaknut.filesystem.DirectoryTitled
   :members:

.. autoclass:: oaknut.filesystem.Bootable
   :members:

.. autoclass:: oaknut.filesystem.FreeSpace
   :members:

.. autoclass:: oaknut.filesystem.FreeMap
   :members:

.. autoclass:: oaknut.filesystem.FreeMapData
   :members:

.. autoclass:: oaknut.filesystem.Sized
   :members:

.. autoclass:: oaknut.filesystem.PhysicalGeometry
   :members:

.. autoclass:: oaknut.filesystem.DiscGeometry
   :members:

.. autoclass:: oaknut.filesystem.Compactable
   :members:

.. autoclass:: oaknut.filesystem.Validatable
   :members:

.. autoclass:: oaknut.filesystem.StatusReporting
   :members:

.. autoclass:: oaknut.filesystem.StorageOrdered
   :members:

.. autoclass:: oaknut.filesystem.WildcardMatching
   :members:

.. autoclass:: oaknut.filesystem.WildcardSyntax
   :members:

.. autoclass:: oaknut.filesystem.NameGrammar
   :members:

.. autoclass:: oaknut.filesystem.UserDatabase
   :members:

.. autoclass:: oaknut.filesystem.RegionHost
   :members:


Geometry
--------

The physical layout beneath a filesystem. A filesystem declares a
:class:`~oaknut.filesystem.GeometryGrammar` (named presets plus a
parameterised form), ``--geometry`` is resolved against it, and
:meth:`~oaknut.filesystem.Filesystem.probe` proposes one in the same
terms.

.. autoclass:: oaknut.filesystem.Geometry
   :members:

.. autoclass:: oaknut.filesystem.GeometryGrammar
   :members:

.. autofunction:: oaknut.filesystem.floppy_geometry

.. autofunction:: oaknut.filesystem.winchester_geometry

.. autofunction:: oaknut.filesystem.geometry_from_dsc

.. autofunction:: oaknut.filesystem.region_reader

.. autodata:: oaknut.filesystem.FLOPPY

.. autodata:: oaknut.filesystem.WINCHESTER


Identification
--------------

The result model returned by :func:`~oaknut.filesystem.identify`: a tree
of per-region :class:`~oaknut.filesystem.Identification` nodes, each with
a :class:`~oaknut.filesystem.Confidence` and the
:class:`~oaknut.filesystem.Partition` it describes.

.. autoclass:: oaknut.filesystem.Confidence
   :members:

.. autoclass:: oaknut.filesystem.Identification
   :members:

.. autoclass:: oaknut.filesystem.Partition
   :members:

.. autoclass:: oaknut.filesystem.Volume
   :members:


The coordinator
---------------

Discovery and enumeration over the ``oaknut.filesystem`` axis. Every
installed filesystem package contributes automatically, so the set grows
with what is installed; nothing here imports a concrete filesystem.

.. autofunction:: oaknut.filesystem.identify

.. autofunction:: oaknut.filesystem.filesystem_names

.. autofunction:: oaknut.filesystem.describe_filesystem

.. autofunction:: oaknut.filesystem.create_filesystem

.. autofunction:: oaknut.filesystem.creating_filesystem


Reading images
--------------

.. autoclass:: oaknut.filesystem.ImageReader
   :members:

.. autodata:: oaknut.filesystem.ImageSource

.. autofunction:: oaknut.filesystem.reader_for


Exceptions
----------

.. autoexception:: oaknut.filesystem.FilesystemError

.. autoexception:: oaknut.filesystem.GeometryError

.. autoexception:: oaknut.filesystem.NoSuchVolumeError

.. autoexception:: oaknut.filesystem.VolumeNotFormattedError

.. autoexception:: oaknut.filesystem.ReadOnlyFilesystemError

.. autoexception:: oaknut.filesystem.FilesystemExtensionError

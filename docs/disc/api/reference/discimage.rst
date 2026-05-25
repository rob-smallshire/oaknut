``oaknut.discimage``
====================

The sector-level layer beneath every disc-backed filesystem. It has no
notion of catalogues or files; it models the physical shape of a disc
image and hands out byte-addressable views of its sectors.

The pieces fit together bottom-up: a :class:`~oaknut.discimage.DiscImage`
wraps a byte buffer and one or more :class:`~oaknut.discimage.Surface`
sides, each described by a :class:`~oaknut.discimage.SurfaceSpec`
geometry. A range of sectors is returned as a
:class:`~oaknut.discimage.SectorsView` that reads and writes straight
through to the buffer, and :class:`~oaknut.discimage.UnifiedDisc`
flattens several surfaces into the single linear address space ADFS
expects. A :class:`~oaknut.discimage.DiscFormat`, built from the
surface-spec helpers, names a complete geometry plus its catalogue
type; filesystem packages compose these into concrete format constants
of their own.

Every name documented here is importable directly from
``oaknut.discimage``.


The disc image
--------------

.. autoclass:: oaknut.discimage.DiscImage
   :members:

.. autoclass:: oaknut.discimage.Surface
   :members:

.. autoclass:: oaknut.discimage.SurfaceSpec
   :members:


Sector access
-------------

.. autoclass:: oaknut.discimage.SectorsView
   :members:

.. autoclass:: oaknut.discimage.UnifiedDisc
   :members:


Disc formats
------------

A :class:`~oaknut.discimage.DiscFormat` is a list of surface specs plus
the catalogue type that lives on them. The helpers build the
:class:`~oaknut.discimage.SurfaceSpec` lists for the three common
physical layouts, so a filesystem package rarely constructs a
``SurfaceSpec`` by hand.

.. autoclass:: oaknut.discimage.DiscFormat
   :members:

.. autofunction:: oaknut.discimage.single_sided_spec

.. autofunction:: oaknut.discimage.interleaved_double_sided_specs

.. autofunction:: oaknut.discimage.sequential_double_sided_specs

.. autodata:: oaknut.discimage.BYTES_PER_SECTOR


Opening an image file
---------------------

.. autofunction:: oaknut.discimage.open_image_mmap

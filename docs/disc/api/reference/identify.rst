``oaknut.identify``
===================

Content-based identification of Acorn disc-image formats. Disc-image
extensions are conventions that are often missing or wrong; this
package answers "what is actually in this image?" by reading the bytes.

A cascade of pluggable :class:`~oaknut.identify.Prober` extensions —
discovered through the ``oaknut.prober`` entry-point namespace (see
:doc:`extension`) — inspect the image and emit ranked
:class:`~oaknut.identify.Identification` candidates. Each carries a
:class:`~oaknut.identify.Confidence` level (from ``CERTAIN`` down to
``POSSIBLE``), human-readable evidence, the concrete
:class:`~oaknut.discimage.DiscFormat` when geometry is determinable
plus any equally-plausible alternatives, and any nested
sub-identifications (an ADFS host with an AFS tail, say).

The file extension is only a tie-breaker between equally-confident
candidates, never the authority.

Every name documented here is importable directly from
``oaknut.identify``.


Identifying an image
--------------------

.. autofunction:: oaknut.identify.identify


Results
-------

.. autoclass:: oaknut.identify.Identification
   :members:

.. autoclass:: oaknut.identify.Confidence
   :members:


Writing a prober
----------------

.. autoclass:: oaknut.identify.Prober
   :members:

.. autoclass:: oaknut.identify.ImageReader
   :members:

.. autofunction:: oaknut.identify.reader_for

.. autodata:: oaknut.identify.ImageSource


The prober axis
---------------

These mirror the per-axis convenience layer every oaknut extension axis
grows on top of :doc:`extension`.

.. autofunction:: oaknut.identify.prober_names

.. autofunction:: oaknut.identify.describe_prober

.. autofunction:: oaknut.identify.create_prober

.. autodata:: oaknut.identify.PROBER_KIND

.. autodata:: oaknut.identify.PROBER_NAMESPACE

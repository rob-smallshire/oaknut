``oaknut.hfe``
==============

HFE (HxC Floppy Emulator) flux images, read-only. An HFE file records
each track as the bitstream the drive head delivers, so reading one is a
pipeline: the container yields each track's flux samples, the decoder
finds the FM and MFM sectors on them, and flattening lays the standard
sectors out as the sector image a filesystem reads.

You rarely need this package directly: it registers
:class:`~oaknut.hfe.HFEDecoder` on the ``oaknut.decoder`` axis, so
:func:`~oaknut.filesystem.reader_for`, and with it every ``disc``
command, opens an HFE file as its flattened sector image. Use it to
look below the sector level, at the copy protection on an original disc
for instance.

.. testsetup::

   from pathlib import Path
   import oaknut.hfe

   # The workspace's test fixtures, found from the editable install.
   _ROOT = Path(oaknut.hfe.__file__).resolve().parents[5]
   DUNJUNZ_S1_FILEPATH = (
       _ROOT / "tests/data/images/hfe/Dunjunz_D1S1_40T_HG3_8518BF40_1.hfe"
   )

.. doctest::

   >>> from oaknut.hfe import HFEImage, analyse, decode_image, flatten
   >>> disc = decode_image(HFEImage.from_filepath(DUNJUNZ_S1_FILEPATH))
   >>> flat = flatten(disc)
   >>> flat.layout.num_tracks, flat.layout.sectors_per_track, flat.suffix
   (40, 10, '.ssd')
   >>> [(f.track, f.remarks) for f in analyse(disc, flat.layout) if f.anomalous]
   [(40, ('unformatted',))]

Every name documented here is importable directly from ``oaknut.hfe``.


The container
-------------

.. automodule:: oaknut.hfe.container
   :no-members:

.. autoclass:: oaknut.hfe.HFEImage
   :members:

.. autoclass:: oaknut.hfe.HFEHeader
   :members:

.. autoclass:: oaknut.hfe.TrackSamples
   :members:

.. autoclass:: oaknut.hfe.TrackEncoding
   :members:
   :undoc-members:

.. autodata:: oaknut.hfe.HFE_V1_SIGNATURE

.. autodata:: oaknut.hfe.HFE_V3_SIGNATURE

.. autofunction:: oaknut.hfe.write_hfe


Decoding tracks
---------------

.. automodule:: oaknut.hfe.decode
   :no-members:

.. autoclass:: oaknut.hfe.Encoding
   :members:
   :undoc-members:

.. autoclass:: oaknut.hfe.DataMark
   :members:
   :undoc-members:

.. autoclass:: oaknut.hfe.SectorID
   :members:

.. autoclass:: oaknut.hfe.DecodedSector
   :members:

.. autoclass:: oaknut.hfe.DecodedTrack
   :members:

.. autoclass:: oaknut.hfe.DecodedDisc
   :members:

.. autofunction:: oaknut.hfe.decode_track

.. autofunction:: oaknut.hfe.decode_image


Flattening to a sector image
----------------------------

.. automodule:: oaknut.hfe.flat
   :no-members:

.. autoclass:: oaknut.hfe.SectorLayout
   :members:

.. autoclass:: oaknut.hfe.FlatImage
   :members:

.. autofunction:: oaknut.hfe.flatten

.. autofunction:: oaknut.hfe.flatten_hfe


The sector report
-----------------

.. automodule:: oaknut.hfe.report
   :no-members:

.. autoclass:: oaknut.hfe.TrackFinding
   :members:

.. autoclass:: oaknut.hfe.SectorFinding
   :members:

.. autofunction:: oaknut.hfe.analyse


Building tracks
---------------

.. automodule:: oaknut.hfe.build
   :no-members:

.. autoclass:: oaknut.hfe.FormattedSector
   :members:

.. autofunction:: oaknut.hfe.build_track

.. autofunction:: oaknut.hfe.track_samples

.. autofunction:: oaknut.hfe.samples_per_half_cell

.. autodata:: oaknut.hfe.TRACK_SAMPLES_300RPM_250KBPS


The decoder plug-in
-------------------

.. autoclass:: oaknut.hfe.HFEDecoder
   :members: recognises, decode


Exceptions
----------

.. autoexception:: oaknut.hfe.HFEError

.. autoexception:: oaknut.hfe.HFEFormatError

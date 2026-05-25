``oaknut.file``
===============

The shared metadata layer every other ``oaknut-*`` package builds on.
It knows nothing of disc images or catalogues; it deals only in the
side-channel metadata an Acorn file carries — load and execution
addresses, the access byte, RISC OS filetypes — and the several
host-side representations that metadata can travel in: INF sidecars,
extended attributes, encoded filenames, and the ``acorn`` text codec.

Every name documented here is importable directly from ``oaknut.file``.


Core types
----------

The central metadata types and the host round-trip helpers are
introduced, with worked examples, in the API patterns rather than
repeated here:

- :class:`~oaknut.file.AcornMeta` — the canonical per-file metadata
  record — and the :class:`~oaknut.file.Access` and
  :class:`~oaknut.file.BootOption` flag enums: see
  :doc:`/api/patterns/metadata`.
- :class:`~oaknut.file.MetaFormat`, naming the host side-channels, with
  the :func:`~oaknut.file.export_with_metadata` and
  :func:`~oaknut.file.import_with_metadata` helpers that move bytes plus
  metadata across the host boundary: also :doc:`/api/patterns/metadata`.
- :class:`~oaknut.file.AcornPath`, the path type the filesystems
  return: see :doc:`/api/patterns/paths`.


Errors
------

The filesystem exception hierarchy. Each inherits from
:class:`~oaknut.exception.DataError`; the broader error model and the
``handled_errors`` boundary are covered in :doc:`/api/patterns/errors`.

.. autoexception:: oaknut.file.FSError

.. autoexception:: oaknut.file.FilesystemClosedError

.. autoexception:: oaknut.file.TitleNotSupportedError

.. autoexception:: oaknut.file.InvalidAddressError


Load and execution addresses
----------------------------

.. autofunction:: oaknut.file.parse_address


Access flags
------------

The :class:`~oaknut.file.Access` enum (see :doc:`/api/patterns/metadata`)
is the in-memory form; these helpers convert to and from the textual
and hexadecimal representations used in INF sidecars and CLI output.

.. autofunction:: oaknut.file.parse_access

.. autofunction:: oaknut.file.format_access_text

.. autofunction:: oaknut.file.format_access_hex


INF sidecars
------------

Reading and writing the ``.inf`` sidecar lines that carry metadata
alongside a plain data file, in both the traditional and PiEconetBridge
flavours.

.. autofunction:: oaknut.file.parse_inf_line

.. autofunction:: oaknut.file.format_trad_inf_line

.. autofunction:: oaknut.file.format_pieb_inf_line

.. autofunction:: oaknut.file.read_inf_file

.. autofunction:: oaknut.file.write_inf_file


Filename encoding
-----------------

Metadata encoded into the filename itself — the ``name,xxx`` filetype
suffix and the ``name,llllllll,eeeeeeee`` load/exec forms.

.. autofunction:: oaknut.file.parse_encoded_filename

.. autofunction:: oaknut.file.build_filename_suffix

.. autofunction:: oaknut.file.build_mos_filename_suffix


Extended attributes
--------------------

Reading and writing metadata in host filesystem extended attributes,
under both the ``user.acorn.*`` namespace and the PiEconetBridge
``user.econet_*`` convention.

.. autofunction:: oaknut.file.read_acorn_xattrs

.. autofunction:: oaknut.file.write_acorn_xattrs

.. autofunction:: oaknut.file.read_econet_xattrs

.. autofunction:: oaknut.file.write_econet_xattrs


The ``acorn`` text codec
------------------------

Importing :mod:`oaknut.file` registers an ``acorn`` text codec, so
``data.decode("acorn")`` works anywhere; these are the direct entry
points for the same conversion.

.. autofunction:: oaknut.file.decode_text

.. autofunction:: oaknut.file.encode_text


Metadata source labels
----------------------

String labels naming where a piece of metadata was resolved from.
The parsing helpers return one of these, and the CLI reports it.

.. autodata:: oaknut.file.SOURCE_DIR

.. autodata:: oaknut.file.SOURCE_FILENAME

.. autodata:: oaknut.file.SOURCE_INF_TRAD

.. autodata:: oaknut.file.SOURCE_INF_PIEB

.. autodata:: oaknut.file.SOURCE_SPARKFS

.. autodata:: oaknut.file.SOURCE_XATTR_ACORN

.. autodata:: oaknut.file.SOURCE_XATTR_PIEB


Default metadata formats
------------------------

The formats the host-bridge helpers fall back to; the import cascade is
discussed under :doc:`/api/patterns/metadata`.

.. autodata:: oaknut.file.DEFAULT_EXPORT_META_FORMAT

.. autodata:: oaknut.file.DEFAULT_IMPORT_META_FORMATS


Host filesystem helpers
-----------------------

.. autofunction:: oaknut.file.copy_file

.. autoclass:: oaknut.file.Stat
   :members:

.. autofunction:: oaknut.file.resolving_io

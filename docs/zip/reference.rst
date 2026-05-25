API reference
=============

Every name below is importable directly from the ``oaknut.zip``
namespace, e.g. ``from oaknut.zip import list_archive``.

The library is function-shaped: there is no archive object to
construct. Each entry point takes a path to a ``.zip`` file and works
against the standard-library :class:`zipfile.ZipFile` underneath. The
metadata it recovers is carried in the shared
:class:`~oaknut.file.AcornMeta` dataclass and the
:class:`~oaknut.file.MetaFormat` enum from :mod:`oaknut.file`.


Inspecting an archive
---------------------

.. autofunction:: oaknut.zip.list_archive

.. autofunction:: oaknut.zip.archive_info

Both return ordinary dictionaries; the symbolic keys they use are
documented under `Result dictionary keys`_ below.


Extracting an archive
---------------------

.. autofunction:: oaknut.zip.extract_archive

.. autofunction:: oaknut.zip.extract_member

.. autofunction:: oaknut.zip.sanitise_extract_path

``extract_archive`` is the high-level entry point most callers want;
``extract_member`` exposes the per-entry mechanics for code that drives
its own iteration over a :class:`zipfile.ZipFile`. ``sanitise_extract_path``
is the traversal guard both rely on, surfaced for reuse.


Parsing and metadata resolution
--------------------------------

These functions implement the three-source resolution described on the
:doc:`index` page — they are exposed for callers that need to inspect a
single source in isolation rather than the resolved result.

.. autofunction:: oaknut.zip.parse_sparkfs_extra

.. autofunction:: oaknut.zip.build_inf_index

.. autofunction:: oaknut.zip.resolve_metadata


Result dictionary keys
----------------------

``list_archive`` and ``archive_info`` return stringly-keyed dicts.
These module-level constants name those keys so callers need not
hard-code the strings.

Per-entry keys — one dict per member from ``list_archive``:

.. autodata:: oaknut.zip.FILENAME_KEY
.. autodata:: oaknut.zip.IS_DIR_KEY
.. autodata:: oaknut.zip.FILE_SIZE_KEY
.. autodata:: oaknut.zip.LOAD_ADDR_KEY
.. autodata:: oaknut.zip.EXEC_ADDR_KEY
.. autodata:: oaknut.zip.ATTR_KEY
.. autodata:: oaknut.zip.FILETYPE_KEY
.. autodata:: oaknut.zip.SOURCE_KEY

Summary keys — the single dict returned by ``archive_info``:

.. autodata:: oaknut.zip.TOTAL_KEY
.. autodata:: oaknut.zip.DIRS_KEY
.. autodata:: oaknut.zip.SPARKFS_COUNT_KEY
.. autodata:: oaknut.zip.INF_COUNT_KEY
.. autodata:: oaknut.zip.PIEB_INF_COUNT_KEY
.. autodata:: oaknut.zip.FILENAME_COUNT_KEY
.. autodata:: oaknut.zip.PLAIN_COUNT_KEY
.. autodata:: oaknut.zip.FILETYPES_KEY

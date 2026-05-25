``oaknut.dfs``
==============

Acorn DFS, Watford DDFS, and Opus DDOS — the flat-catalogue filesystems
of BBC Micro and Acorn Electron floppies, in ``.ssd`` / ``.dsd`` form.
A single catalogue holds up to 31 files (62 under Watford DDFS), each
with a one-character directory, a seven-character name, and load/exec
addresses; there is no directory hierarchy.

Every name documented here is importable directly from ``oaknut.dfs``.


The filesystem
--------------

.. autoclass:: oaknut.dfs.DFS
   :members:

.. autoclass:: oaknut.dfs.DFSPath
   :members:

.. autoclass:: oaknut.dfs.DFSStat
   :members:

.. autoclass:: oaknut.dfs.DiscInfo
   :members:


Detecting and sizing images
---------------------------

.. autofunction:: oaknut.dfs.detect_dfs_format

.. autofunction:: oaknut.dfs.expand


Disc formats
------------

The format constants for the standard Acorn DFS geometries — 40- and
80-track, single- and double-sided (sequential or interleaved). Each is
a generic :class:`~oaknut.discimage.DiscFormat`. Watford DDFS catalogues
are detected at read time and need no separate format constant here.

.. autodata:: oaknut.dfs.ACORN_DFS_40T_SINGLE_SIDED

.. autodata:: oaknut.dfs.ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED

.. autodata:: oaknut.dfs.ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL

.. autodata:: oaknut.dfs.ACORN_DFS_80T_SINGLE_SIDED

.. autodata:: oaknut.dfs.ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED

.. autodata:: oaknut.dfs.ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL

.. autodata:: oaknut.dfs.IMAGE_FORMAT_BY_EXTENSION


See also
--------

The shared metadata types that appear throughout the DFS API —
:class:`~oaknut.file.AcornMeta`, the :class:`~oaknut.file.BootOption`
and :class:`~oaknut.file.MetaFormat` enums, the
:class:`~oaknut.file.FSError` base, and the host-bridge import/export
helpers — belong to :doc:`oaknut.file <file>`; the generic
:class:`~oaknut.discimage.DiscFormat` belongs to
:doc:`oaknut.discimage <discimage>`. Import them from the package that
owns them.

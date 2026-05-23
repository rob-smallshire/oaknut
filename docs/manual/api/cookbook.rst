API cookbook
============

Worked examples that compose the Python API to solve realistic tasks.
Each recipe is a runnable script under ``scripts/api-examples/`` whose
source and output are embedded into this page at build time, so the
shown code is the code we test in CI.

.. note::

   This page is a placeholder. Anticipated recipes include:

   - reading every file off a DFS floppy into a host directory tree
   - creating a fresh ADFS hard disc and seeding it
   - mirroring a directory tree into an AFS server disc with
     :func:`oaknut.afs.host_import.import_tree`
   - decoding a BBC BASIC tokenised file with
     :func:`oaknut.basic.detokenise`
   - re-packing a ZIP archive of Acorn files and preserving load /
     exec metadata via :mod:`oaknut.zip`

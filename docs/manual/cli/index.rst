Command-line interface
======================

The ``disc`` command-line tool is how most readers will interact with
oaknut. It speaks DFS, ADFS, and AFS transparently from a single
binary, with a flat ``git``-style subcommand surface (``disc ls``,
``disc cp``, ``disc afs-init``, …) and Acorn star-aliases (``*CAT``,
``*RENAME``, …) for muscle-memory.

If you are writing Python code that consumes the on-disc formats
directly rather than driving the CLI, see :doc:`/api/index` instead.

.. toctree::
   :maxdepth: 1
   :caption: Getting started

   getting-started

.. toctree::
   :maxdepth: 1
   :caption: How-to

   cookbook

.. toctree::
   :maxdepth: 1
   :caption: Reference

   conventions/index
   commands/index

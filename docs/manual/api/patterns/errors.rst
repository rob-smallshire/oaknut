Error handling
==============

Every package raises subclasses of :class:`oaknut.file.FSError`, so a
single ``except FSError`` is the canonical way to handle filesystem
problems across DFS, ADFS, AFS, and ZIP.

.. note::

   This page is a placeholder. Final content will cover:

   - the ``FSError`` class hierarchy and what each subclass means
   - which operations raise which errors
   - the ``code`` attribute that mirrors the on-the-wire Acorn FS
     error code, and when to switch on it vs. catching by type
   - how the CLI translates these errors into exit codes and
     ``Error: …`` messages (see :doc:`/cli/conventions/exit-codes`)

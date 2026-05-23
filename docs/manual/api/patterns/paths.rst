Path objects
============

Each filing system exposes a path object with a uniform interface
modelled loosely on :class:`pathlib.Path`. Once you have a path, you
can ``iterdir()``, ``stat()``, ``read_bytes()``, ``write_bytes()`` and
slash-join it regardless of which filesystem owns it.

.. note::

   This page is a placeholder. Final content will cover:

   - :class:`oaknut.dfs.DFSPath`, :class:`oaknut.adfs.ADFSPath`,
     :class:`oaknut.afs.AFSPath`
   - the slash-join operator, ``^`` for the parent directory
   - methods all path classes share, and where they diverge
   - using these paths inside ``with FS.from_file(...) as fs:``
     contexts — paths bind to a filesystem handle and become stale
     when it closes

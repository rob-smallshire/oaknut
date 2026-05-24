Getting started
===============

The oaknut Python API lets you read, write, and round-trip Acorn DFS,
ADFS, and AFS disc images from inside a Python program. The shape
of the API is deliberately close to :class:`pathlib.Path` so that
``image.root / "Games" / "Elite"`` reads the same as a host path.

This page walks from "I have a disc image" to "I am confident
reading and writing files" in about ten minutes. Every snippet is
runnable as-is — paste it into a REPL or a script. If you have not
yet installed any oaknut packages, see :doc:`/install`. If you do
not have a real Acorn image handy, the :ref:`api-first-disc`
section below builds a blank one to follow along with.


First contact
-------------

Three operations cover the common case of "look at one directory,
look at the whole disc, read one file":

.. code-block:: python

   from oaknut.dfs import DFS

   with DFS.from_file("Disc003-Zalaga.ssd") as dfs:
       print(dfs.title)

       # The contents of the default directory, $.
       for entry in (dfs.root / "$").iterdir():
           print(entry.name)

       # Every file on the disc, across every populated letter.
       for dirpath, _dirs, filenames in dfs.root.walk():
           for filename in filenames:
               print(f"{dirpath.path}.{filename}")

       # Read one file's bytes.
       data = (dfs.root / "$" / "ZALAGA").read_bytes()

Every filesystem class follows the same shape: ``from_file`` is a
named-constructor context manager, ``.root`` is the catalogue handle,
:meth:`iterdir` yields children, :meth:`walk` recurses, and the
slash operator joins path components. Swap ``DFS`` for
:class:`oaknut.adfs.ADFS` or :class:`oaknut.afs.AFS` and the rest of
the code reads identically.

On DFS specifically, ``$`` is a child of the nameless root, just
like any other single-character directory name. On a real BBC Micro
it is the default current directory after boot. ``dfs.root /
"$"`` selects that child, and iterating it yields the files filed
under ``$``. ADFS and AFS differ: on those filesystems ``$``
*is* the root, so ``adfs.root.iterdir()`` yields the children of
``$`` directly.


.. _api-first-disc:

Build a blank disc to follow along
----------------------------------

:meth:`DFS.create_file <oaknut.dfs.DFS.create_file>` makes a fresh
image you can write into. We will use a single-sided BBC Micro
floppy (SSD) — small, fast, and what most Acorn-era discs in the
wild are.

.. code-block:: python

   from pathlib import Path
   from oaknut.dfs import DFS

   filepath = Path("hello.ssd")
   with DFS.create_file(filepath, title="GETSTART"):
       pass

The yielded handle is a writable :class:`DFS` instance. The
``with`` block here is empty because we just want the empty disc;
the next sections fill it. The ``.ssd`` extension is enough for
``create_file`` to pick the canonical 80-track single-sided format;
``.dsd`` would give you the 80-track double-sided interleaved one.
Pass an explicit :class:`DiscFormat` for the 40-track or
sequential-double-sided variants.

ADFS and AFS have the same ``create_file`` shape. ADFS picks the
floppy format from the extension too — ``.ads`` ⇒ ADFS_S,
``.adm`` ⇒ ADFS_M, ``.adl`` ⇒ ADFS_L — and ``.adf`` is the lone
ambiguous case that still needs an explicit argument:

.. code-block:: python

   from oaknut.adfs import ADFS

   with ADFS.create_file("hello.adl", title="GETSTART"):
       pass

AFS lives in the tail of an ADFS hard-disc image, and
:meth:`AFS.create_file <oaknut.afs.AFS.create_file>` orchestrates
both partitions in one call. See the cookbook recipe
:doc:`cookbook` for the full walkthrough.


Put files in
------------

Three write methods, mirroring :class:`pathlib.Path`:

.. code-block:: python

   from oaknut.file import Access

   with DFS.from_file("hello.ssd") as dfs:
       (dfs.root / "$.README").write_text(
           "Welcome to GETSTART.\n",
       )
       (dfs.root / "$.PROG").write_bytes(
           b"\xa9\x41\x20\xee\xff\x60",     # LDA #'A' : JSR &FFEE : RTS
           load_address=0x1900,
           exec_address=0x1900,
       )
       (dfs.root / "$.STUB").touch(access=Access.LWR)

:meth:`write_text` encodes via the Acorn character set and
translates Python ``"\n"`` to the on-disc ``"\r"`` line terminator
by default — pass ``newline=""`` to preserve whatever terminators
your string already has. :meth:`write_bytes` writes raw bytes plus
optional ``load_address``, ``exec_address``, and ``access``.
:meth:`touch` creates an empty file (skip it if it already exists,
matching :meth:`pathlib.Path.touch`).

``access`` accepts :class:`oaknut.file.Access` flags;
:attr:`Access.LWR` is the canonical "locked owner R+W",
:attr:`Access.WR` is unlocked owner R+W (the default if you omit
``access`` entirely).

Mutations made inside the ``with`` block are flushed when the
context exits cleanly; an exception inside the block discards them.
There is no separate ``commit`` step.


Read files out
--------------

The symmetric three:

.. code-block:: python

   with DFS.from_file("hello.ssd") as dfs:
       data = (dfs.root / "$.PROG").read_bytes()
       text = (dfs.root / "$.README").read_text()
       st   = (dfs.root / "$.PROG").stat()

:meth:`read_text` applies universal-newline translation by default
(``"\r"``, ``"\r\n"``, and ``"\n"`` all become ``"\n"`` in the
returned string). :meth:`stat` returns an :class:`oaknut.file.Stat`
with ``.length``, ``.load_address``, ``.exec_address``, and
``.access`` — the same shape across all three filesystems.


Walking the catalogue
---------------------

ADFS and AFS are hierarchical, so the natural traversal is a tree
walk. :meth:`walk` mirrors :meth:`pathlib.Path.walk`: each step
yields ``(dirpath, dirnames, filenames)`` in pre-order:

.. code-block:: python

   from oaknut.adfs import ADFS

   with ADFS.from_file("disc.adl") as adfs:
       for dirpath, dirnames, filenames in adfs.root.walk():
           print(dirpath.path)
           for filename in filenames:
               print(f"  {filename}")

The same call works against :class:`oaknut.dfs.DFSPath` and
:class:`oaknut.afs.AFSPath`. For a one-level listing without
descending, use :meth:`iterdir`.

For creating subdirectories, :meth:`mkdir` mirrors pathlib too —
including ``parents=True`` (create missing intermediates) and
``exist_ok=True`` (suppress the error when the directory already
exists, as long as the existing entry is itself a directory).

DFS images do not nest. The catalogue is flat and the
single-character directory names (``$``, ``A``–``Z``) all sit as
siblings under the nameless root, so :meth:`mkdir` does not exist
on :class:`DFSPath`. :meth:`walk` does work: starting from
``dfs.root`` it visits the nameless root once, then yields one
tuple per populated directory letter — the canonical way to see
every file on the disc without first knowing which letters are in
use. See :doc:`patterns/paths` for the full model.


A real Acorn disc: Repton Infinity
----------------------------------

Everything above works unchanged against released Acorn-era discs.
Open Superior Software's *Repton Infinity* (1988):

.. code-block:: python

   from oaknut.dfs import DFS
   from oaknut.dfs.formats import ACORN_DFS_80T_SINGLE_SIDED

   with DFS.from_file("Disc999-ReptonInfinity.ssd",
                      ACORN_DFS_80T_SINGLE_SIDED) as dfs:
       print(f"Title:       {dfs.title}")
       print(f"Boot option: {dfs.boot_option.name}")
       for entry in dfs.root.iterdir():
           st = entry.stat()
           print(f"  {entry.path:14s}  load={st.load_address:#010x}  "
                 f"size={st.length:>5d}")

       boot = (dfs.root / "$.!BOOT").read_text()
       print(boot)

The disc's boot option is ``EXEC``: pressing :kbd:`SHIFT-BREAK` on
a real BBC effectively types ``*EXEC $.!BOOT``, so the contents of
``!BOOT`` run as if each line had been typed at the OS prompt.
``read_text`` does the ``"\r"`` → ``"\n"`` translation so the file
reads cleanly without ``cat -v`` tricks.

The :doc:`CLI walkthrough </cli/getting-started>` runs the same
disc through ``disc`` from the shell.


When something fails
--------------------

Every oaknut error inherits from
:class:`oaknut.exception.OaknutException`. A small set of category
subclasses — :class:`DataError`, :class:`ConfigurationError`,
:class:`InternalError` — sits directly under it. Filesystem-specific
errors like :class:`oaknut.adfs.ADFSPathError` or
:class:`oaknut.afs.AFSDirectoryEntryExistsError` all inherit from
:class:`FSError`, which is itself a :class:`DataError`.

.. code-block:: python

   from oaknut.adfs import ADFS, ADFSPathError

   with ADFS.from_file("disc.adl") as adfs:
       try:
           (adfs.root / "Missing").read_bytes()
       except ADFSPathError as exc:
           print(f"oops: {exc}")

See :doc:`patterns/errors` for the full hierarchy and the
:func:`oaknut.exception.handled_errors` CLI-boundary helper that
turns these into one-line error messages and exit codes.


Where to go next
----------------

- :doc:`cookbook` — eight tested, runnable recipes for the operations
  this page introduced (cross-image copy, host round-trip, building a
  Level 3 File Server disc, bulk-archiving floppies).
- :doc:`patterns/index` — cross-cutting concepts that span the package
  boundaries (paths, metadata, errors).
- :doc:`reference/index` — the per-package autodoc for every public
  class, method, and function.
- :doc:`/cli/getting-started` if you would rather drive the same
  operations from a shell than from Python.

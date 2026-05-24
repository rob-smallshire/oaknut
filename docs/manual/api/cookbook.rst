API cookbook
============

Use the Python API when you need to compose Acorn-filesystem
operations inside a larger Python program — building a disc image
as part of an asset pipeline, scripting WFSINIT setup across many
discs, integrating with an emulator, or implementing a feature the
CLI does not yet expose. For ad-hoc operations from a shell, the
:doc:`/cli/getting-started` walkthrough is usually the friendlier
starting point.

Each recipe below is a complete, runnable Python file in
``scripts/api-examples/``. The test suite exercises every recipe at
each release (``test_api_examples.py``) so the code on this page is
guaranteed to match the live API.


Opening a disc and listing its contents
---------------------------------------

The simplest read pattern: hand a disc-image path to ``DFS.from_file``
inside a ``with`` block, then iterate the catalogue. The recipe below
loops through every directory letter (``$``, ``A``, ``B``, …) and
prints each entry's metadata via the unified :class:`oaknut.file.Stat`
protocol — the same ``.access``, ``.length``, ``.load_address`` work
without per-filesystem branching.

Two things to notice:

- ``DFS.from_file(filepath)`` auto-detects the format from the file's
  extension and size — no explicit ``ACORN_DFS_80T_SINGLE_SIDED``
  argument is needed for ``.ssd`` / ``.dsd`` images of standard
  sizes. Pass ``disk_format=`` if you have an oddball image.
- DFS's *flat* catalogue means iteration is two levels: each
  ``dfs.root`` child is a populated directory letter, and each of
  those iterates as its files. See :doc:`/cli/conventions/paths` for
  the model in full.

.. literalinclude:: ../../../scripts/api-examples/list_dfs_disc.py
   :language: python
   :pyobject: list_disc


Walking an ADFS tree recursively
--------------------------------

ADFS (and AFS, with the same API) is hierarchical: ``$`` contains
named subdirectories, which contain further files and directories.
The natural read pattern is recursion. The function below is
``os.walk`` in spirit but built from oaknut primitives —
:meth:`ADFSPath.iterdir` for descending and :meth:`ADFSPath.is_dir`
to decide whether to recurse. The same function works unchanged on
an :class:`oaknut.afs.AFSPath`.

.. literalinclude:: ../../../scripts/api-examples/walk_adfs_tree.py
   :language: python
   :pyobject: walk_tree


Creating a disc with varied entries
-----------------------------------

The write side mirrors the read side: a context-manager constructor
plus per-path methods to put bytes on disc. ``write_text`` accepts
arbitrary strings and Acorn-encodes them; ``write_bytes`` takes raw
data plus load/exec addresses and the unified ``access`` keyword.

The locked shortcut — ``access=True`` — is shorthand for setting
``Access.L`` and the filesystem's default owner R+W bits. Pass an
explicit :class:`oaknut.file.Access` flag pattern for fine-grained
control (owner-execute, public-read, …) on filesystems that store
them.

.. literalinclude:: ../../../scripts/api-examples/create_dfs_disc.py
   :language: python
   :pyobject: populate_disc


Round-tripping a file through the host filesystem
-------------------------------------------------

The symmetric :meth:`export_file` / :meth:`import_file` methods live
on every path class. Combined with a :class:`oaknut.file.MetaFormat`
they preserve load address, exec address, and access bits across the
host crossing — no manual :class:`oaknut.file.AcornMeta` assembly,
no per-format glue in the caller.

The recipe walks the source disc, drops every file plus its INF
sidecar onto the host, then re-imports each into a fresh disc — and
finally asserts the bytes and metadata round-tripped intact.

.. literalinclude:: ../../../scripts/api-examples/round_trip_via_host.py
   :language: python
   :pyobject: round_trip


Copying files across filesystems
--------------------------------

A path's :meth:`copy_to` is sugar over :func:`oaknut.file.copy_file`.
Because every path class shares the unified ``write_bytes`` signature
(including the ``access`` translation), a single call works regardless
of which filesystem the source and destination live on — DFS-to-ADFS
here, but any cross-FS pair is equivalent.

The recipe loops a flat DFS catalogue's entries into the root of an
ADFS hard disc. Each ``entry.copy_to(destination)`` reads the source's
bytes and metadata, maps the locked-bit-only DFS access to the
canonical wire-form ``Access`` flags ADFS understands, and writes
through in one step.

.. literalinclude:: ../../../scripts/api-examples/copy_across_filesystems.py
   :language: python
   :pyobject: cross_copy


Bulk-archiving a folder of floppies onto one hard disc
------------------------------------------------------

The Python counterpart to the CLI cookbook's bulk-archive recipe.
Same shape — one subdirectory on the archive per source SSD, every
file copied across — but inline naming, filtering, or progress hooks
can be wired in as the loop body without going through shell.

The ADFS hard-disc image is sized via ``capacity="10MB"`` —
:func:`oaknut.file.capacity.parse_capacity` parses the string the
same way ``disc create --capacity`` does, so there's no need to
multiply by 1024 by hand.

.. literalinclude:: ../../../scripts/api-examples/bulk_archive_ssds.py
   :language: python
   :pyobject: archive_floppies


Building a Level 3 File Server disc from scratch
------------------------------------------------

:meth:`AFS.create_file` is the top-level orchestrator that composes
:meth:`ADFS.create_file` + :func:`oaknut.afs.initialise` +
:func:`oaknut.afs.emplace_library` into a single named constructor.
The same configuration through the lower-level building blocks would
be twenty lines of composition; this is six.

Inside the yielded ``with`` block the AFS handle is open and
writable, so the recipe finishes by carving a personal directory for
the new user and dropping a note into it — the kind of thing a real
provisioning script does.

.. literalinclude:: ../../../scripts/api-examples/build_l3fs_disc.py
   :language: python
   :pyobject: build_server_disc


Adding a user to an existing AFS image
--------------------------------------

:meth:`AFS.add_user` is the public counterpart to
``disc afs-useradd`` on the CLI. The ``quota`` keyword takes the
same capacity-string form as :meth:`AFS.create_file`, so a setup
script can read user/quota lines from a config file without
translating them into bytes first.

Note the ``mode="r+b"`` on :meth:`AFS.from_file` — the default is
read-only; opening for mutation requires the explicit mode, matching
:meth:`ADFS.from_file`. ``afs.flush()`` at the end of the block
guarantees the new record is on disc before the context exits.

.. literalinclude:: ../../../scripts/api-examples/add_afs_user.py
   :language: python
   :pyobject: add_user

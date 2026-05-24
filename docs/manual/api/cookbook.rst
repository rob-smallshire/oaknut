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

``DFS.from_file`` opens an image as a context manager. ``dfs.root``
is the catalogue handle; iterating it yields one path per populated
directory letter (``$``, ``A``–``Z``), and iterating each of those
yields the files carrying that letter. Per-entry metadata is read
via :meth:`stat`, which returns a :class:`oaknut.file.Stat` with
``.length``, ``.load_address`` and ``.access``.

DFS images are flat: the directory letters are siblings, not
parents and children. See :doc:`/cli/conventions/paths` for the
full model.

.. literalinclude:: ../../../scripts/api-examples/list_dfs_disc.py
   :language: python
   :pyobject: list_disc


Walking an ADFS tree recursively
--------------------------------

ADFS (and AFS) is hierarchical: ``$`` contains named subdirectories
which contain further files and directories. :meth:`iterdir` yields
the immediate children of a path; :meth:`is_dir` says whether each
child is itself a directory to descend into.

The function below recurses depth-first and prints the tree in
filesystem order. The same code runs against an
:class:`oaknut.afs.AFSPath` without modification.

.. literalinclude:: ../../../scripts/api-examples/walk_adfs_tree.py
   :language: python
   :pyobject: walk_tree


Creating a disc with varied entries
-----------------------------------

:meth:`write_bytes` writes a single file with optional ``load_address``,
``exec_address``, and ``access`` keyword arguments. :meth:`write_text`
encodes a string as Acorn bytes first. ``access`` is an
:class:`oaknut.file.Access` flag combination: :attr:`Access.LWR` is
the canonical "locked owner R+W"; :attr:`Access.WR` (or omitting
``access`` entirely) gives unlocked owner R+W.

.. literalinclude:: ../../../scripts/api-examples/create_dfs_disc.py
   :language: python
   :pyobject: populate_disc


Round-tripping a file through the host filesystem
-------------------------------------------------

:meth:`export_file` writes a file's bytes plus a metadata sidecar
(in the chosen :class:`oaknut.file.MetaFormat`) to a host path.
:meth:`import_file` reads them back. Both methods live on every
path class.

The recipe walks the source disc, exports each file with an INF
sidecar, and re-imports the lot into a fresh disc. The closing
assertions confirm the bytes and metadata are byte-identical on
both sides.

.. literalinclude:: ../../../scripts/api-examples/round_trip_via_host.py
   :language: python
   :pyobject: round_trip


Copying files across filesystems
--------------------------------

:meth:`copy_to` writes the source file's bytes and metadata to a
destination path. The destination's filesystem decides how to
encode the access bits; the call is identical whether the source
and destination share a filesystem family or not.

The recipe copies every file from a DFS catalogue into the root of
an ADFS hard disc.

.. literalinclude:: ../../../scripts/api-examples/copy_across_filesystems.py
   :language: python
   :pyobject: cross_copy


Bulk-archiving a folder of floppies onto one hard disc
------------------------------------------------------

The recipe creates one ADFS subdirectory per source SSD and copies
every file across. The subdirectory name is the first PascalCase
word of the SSD filename — for ``Disc001-PlanetoidAKADefender.ssd``
the chosen name is ``Planetoid`` — and falls back to a truncated
stem when the regex does not match.

.. literalinclude:: ../../../scripts/api-examples/bulk_archive_ssds.py
   :language: python
   :pyobject: archive_floppies


Building a Level 3 File Server disc from scratch
------------------------------------------------

:meth:`AFS.create_file` creates an ADFS hard-disc envelope and
initialises an AFS partition inside it. ``users`` adds accounts on
top of the built-in ``Syst`` / ``Boot`` / ``Welcome`` set;
``omit_users`` removes named built-ins from that set;
``emplacements`` lays down a shipped library image (``"Library"``,
``"Library1"``, ``"ArthurLib"``) or any ``.adl`` path.

The yielded AFS handle is open and writable for the duration of
the ``with`` block, so the recipe finishes by creating a personal
directory for the new user and writing a note into it.

.. literalinclude:: ../../../scripts/api-examples/build_l3fs_disc.py
   :language: python
   :pyobject: build_server_disc


Adding a user to an existing AFS image
--------------------------------------

:meth:`AFS.add_user` appends an account to the passwords file on
an existing AFS image and writes the change back to disc.

The image must be opened with ``mode="r+b"`` — the default ``"rb"``
gives a read-only handle. :meth:`AFS.flush` at the end of the block
guarantees the new record is on disc before the context exits.

.. literalinclude:: ../../../scripts/api-examples/add_afs_user.py
   :language: python
   :pyobject: add_user

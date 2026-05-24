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

The :meth:`DFS.from_file <oaknut.dfs.DFS.from_file>` named
constructor opens an image as a context manager. The
``dfs.root`` attribute is the catalogue handle; iterating it
yields one path per populated directory letter (``$``,
``A``–``Z``), and iterating each of those yields the files
carrying that letter. Per-entry metadata is read via
:meth:`stat`, which returns a :class:`oaknut.file.Stat` with
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
which contain further files and directories. The :meth:`walk`
method mirrors :meth:`pathlib.Path.walk` — each step yields
``(dirpath, dirnames, filenames)`` in pre-order, descending into
every subdirectory. The same call works against
:class:`oaknut.dfs.DFSPath` and :class:`oaknut.afs.AFSPath`.

.. literalinclude:: ../../../scripts/api-examples/walk_adfs_tree.py
   :language: python
   :pyobject: walk_tree


Creating a disc with varied entries
-----------------------------------

The :meth:`write_bytes` method writes a single file with optional
``load_address``, ``exec_address``, and ``access`` keyword
arguments. The :meth:`write_text` companion encodes a string as
Acorn bytes first, translating Python ``"\n"`` to the on-disc
``"\r"`` line terminator in keeping with Python's
universal-newline convention. The ``access`` keyword takes an
:class:`oaknut.file.Access` flag combination: :attr:`Access.LWR`
is the canonical "locked owner R+W"; :attr:`Access.WR` (or
omitting ``access`` entirely) gives unlocked owner R+W.

.. literalinclude:: ../../../scripts/api-examples/create_dfs_disc.py
   :language: python
   :pyobject: populate_disc


Round-tripping a file through the host filesystem
-------------------------------------------------

The :meth:`export_file` method writes a file's bytes plus a
metadata sidecar (in the chosen :class:`oaknut.file.MetaFormat`)
to a host path. The :meth:`import_file` companion reads them
back. Both methods live on every path class.

The recipe walks the source disc, exports each file with an INF
sidecar, and re-imports the lot into a fresh disc. The closing
assertions confirm the bytes and metadata are byte-identical on
both sides.

.. literalinclude:: ../../../scripts/api-examples/round_trip_via_host.py
   :language: python
   :pyobject: round_trip


Copying files across filesystems
--------------------------------

The :meth:`copy_to` method writes the source file's bytes and
metadata to a destination path. The destination's filesystem
decides how to encode the access bits; the call is identical
whether the source and destination share a filesystem family or
not.

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

The :meth:`AFS.create_file <oaknut.afs.AFS.create_file>` named
constructor creates an ADFS hard-disc envelope and initialises
an AFS partition inside it. The ``users`` keyword adds accounts
on top of the built-in ``Syst`` / ``Boot`` / ``Welcome`` set;
``omit_users`` removes named built-ins from that set; and
``emplacements`` lays down a shipped library image
(``"Library"``, ``"Library1"``, ``"ArthurLib"``) or any
``.adl`` path.

The yielded AFS handle is open and writable for the duration of
the ``with`` block, so the recipe finishes by creating a personal
directory for the new user and writing a note into it.

.. literalinclude:: ../../../scripts/api-examples/build_l3fs_disc.py
   :language: python
   :pyobject: build_server_disc


Adding a user to an existing AFS image
--------------------------------------

The :meth:`AFS.add_user <oaknut.afs.AFS.add_user>` method appends
an account to the passwords file. An AFS file server always lives
in the tail of an ADFS hard-disc image, so the recipe opens the
disc as ADFS and reaches the partition through
:meth:`ADFS.open_afs_partition <oaknut.adfs.ADFS.open_afs_partition>`,
which yields the :class:`AFS` handle and calls :meth:`AFS.close` on
clean exit (or :meth:`AFS.discard` if the body raises).

Buffered writes on the AFS side commit when the inner ``with``
block exits cleanly; an exception inside the block discards them,
leaving the on-disc passwords file untouched. The image is opened
writable when the host filesystem permits — no Python ``open()``
mode strings to remember.

.. literalinclude:: ../../../scripts/api-examples/add_afs_user.py
   :language: python
   :pyobject: add_user

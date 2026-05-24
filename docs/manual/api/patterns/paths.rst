Path objects
============

Each filing system exposes a path object with a uniform interface
modelled on :class:`pathlib.Path`. The three concrete classes
inherit from :class:`oaknut.file.AcornPath`, which carries the
shared surface — slash-join, iterdir, stat, read_bytes,
write_bytes, walk, touch, copy_to, and the rest — and delegates
the filesystem-specific primitives to each subclass:

- :class:`oaknut.file.AcornPath` (concrete base, parallel to
  :class:`pathlib.PurePath` / :class:`pathlib.Path`)
- :class:`oaknut.dfs.DFSPath`
- :class:`oaknut.adfs.ADFSPath`
- :class:`oaknut.afs.AFSPath`

Callers wanting "a path on any Acorn filesystem" can type-hint
with :class:`AcornPath` directly::

    from oaknut.file import AcornPath

    def summarise(p: AcornPath) -> None:
        print(p.path, p.stat().length)

A path is obtained from an open filesystem handle::

    with ADFS.from_file("disc.adl") as adfs:
        elite = adfs.root / "Games" / "Elite"
        elite.read_bytes()

Paths bind to a filesystem handle and become stale when the handle
closes — never escape a path out of its ``with`` block and reach
for it later.


Shared shape
------------

Every concrete path class inherits the surface below from
:class:`oaknut.file.AcornPath`, so a function that takes "a path on
any Acorn filesystem" can be written without caring which family
produced it. The methods fall into seven groups: **navigation**
(slash-join and the path properties), **querying** (``exists`` /
``is_dir`` / ``is_file`` / ``stat``), **iteration** (``iterdir``,
``__iter__``, ``walk``), **read** (``read_bytes`` / ``read_text``),
**write** (``write_bytes`` / ``write_text`` / ``touch``), **mutate**
(``rename``, ``unlink``, ``lock`` / ``unlock``, the address
setters), and **host-side round-trip** (``export_file`` /
``import_file`` / ``copy_to``).

The shape mirrors :mod:`pathlib`'s own division:
:class:`AcornPath` plays the role :class:`pathlib.PurePath` and
:class:`pathlib.Path` play in the standard library — a concrete
base with abstract-by-``NotImplementedError`` filesystem primitives
and default implementations for everything that can be expressed in
terms of those primitives.

.. autoclass:: oaknut.file.AcornPath
   :members:
   :special-members: __truediv__, __iter__
   :member-order: bysource

The cookbook recipes lean on this uniformity: code that walks a
directory and prints its contents looks the same on DFS, ADFS, and
AFS.


Where the path models diverge
-----------------------------

The same surface hides a structural difference that bites if you
assume Unix or ADFS shape when reading DFS code.

**ADFS and AFS — hierarchical trees.**
``adfs.root`` and ``afs.root`` are the actual top-level directory
``$``. Walking with ``/`` descends into named subdirectories::

    adfs.root                       # represents $
    adfs.root / "Games"             # $.Games (a directory)
    adfs.root / "Games" / "Elite"   # $.Games.Elite (a file)

``mkdir()`` works on ADFSPath / AFSPath. ``^`` is meaningful (the
parent path). ``iterdir()`` on a subdirectory yields its
immediate children.

**DFS — single-character directories under a nameless root.**
A DFS catalogue holds up to 31 file entries (62 on Watford DDFS).
Each lives in one of 27 directories — ``$`` and ``A``–``Z`` — and
all 27 are children of a nameless root. ``$`` is the default
directory DFS assumes when a path omits one (per the Acorn DFS
User Guide); it is not a parent of ``A``–``Z``, just a sibling
with one extra job::

    dfs.root                       # the nameless root
    dfs.root / "$" / "HELLO"       # $.HELLO in the default directory
    dfs.root / "A" / "GAME"        # A.GAME, a sibling of $.HELLO

Empty directories cannot exist on DFS — a directory comes into
being the first time you write a file under it and disappears
again when its last file is deleted. There is no ``mkdir`` and no
:meth:`DFSPath.mkdir`. ``^`` carries no meaning, since there is no
tree to walk up. :meth:`iterdir` on the nameless root yields one
entry per populated directory letter; :meth:`iterdir` on a
single-letter directory yields the files filed under it.

See :doc:`/cli/conventions/paths` for the CLI-side companion to this
explanation.


Binding to a filesystem handle
------------------------------

A path holds a reference to the filesystem handle it came from. The
handle owns the underlying mmap / file descriptor and flushes on
exit. A path that outlives its handle's ``with`` block is a stale
view onto a closed disc image — reading from it raises::

    with ADFS.from_file("disc.adl") as adfs:
        elite = adfs.root / "Games" / "Elite"
    # adfs is closed now
    elite.read_bytes()      # raises — handle gone

Keep path use inside the ``with`` block, or pull the bytes you need
out before exiting.

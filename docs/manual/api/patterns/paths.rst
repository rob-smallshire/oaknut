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

Every path class implements the same surface, so a function that
takes "a path on any Acorn filesystem" can be written without
caring which family produced it.

**Navigation** (slash-join, properties):

- ``p / "name"`` — slash-join a child component
- ``parent`` — the containing path
- ``name`` — the final component
- ``parts`` — a tuple of components
- ``path`` — the full path string

**Querying:**

- ``exists()`` / ``is_dir()`` / ``is_file()``
- ``stat() -> oaknut.file.Stat`` (the unified :class:`Stat` protocol —
  ``length``, ``load_address``, ``exec_address``, ``access`` as a
  canonical :class:`oaknut.file.Access`, ``is_directory``, ``date``)

**Iteration:**

- ``iterdir()`` and ``__iter__`` — direct children of a directory
- ``walk()`` — :meth:`pathlib.Path.walk`-shaped pre-order traversal
  yielding ``(dirpath, dirnames, filenames)``

**Read:**

- ``read_bytes()``
- ``read_text(*, encoding="acorn", newline=None)`` — applies
  Python's universal-newline translation by default

**Write:**

- ``write_bytes(data, *, load_address=0, exec_address=0,
  access=None, date=None)``
- ``write_text(text, *, encoding="acorn", newline="\r", ...)`` —
  translates Python ``"\n"`` to the Acorn-native ``"\r"`` by default
- ``touch(*, access=None, exist_ok=True)`` —
  :meth:`pathlib.Path.touch`-shaped

**Mutate:**

- ``rename(target) -> Path``
- ``unlink()``
- ``lock()`` / ``unlock()``
- ``set_load_address(addr)`` / ``set_exec_address(addr)``

**Host-side round-trip:**

- ``export_file(host_path, *, meta_format=, owner=)`` /
  ``import_file(source_filepath, *, meta_formats=)``
- ``copy_to(dst)`` — sugar for :func:`oaknut.file.copy_file`

The cookbook recipes lean on this uniformity: code that walks a
directory and prints its contents looks the same on DFS, ADFS, and
AFS.

The shape mirrors :mod:`pathlib`'s own division: :class:`AcornPath`
plays the role :class:`pathlib.PurePath` and :class:`pathlib.Path`
play in the standard library — a concrete base with abstract-by-
``NotImplementedError`` filesystem primitives and default
implementations for everything that can be expressed in terms of
those primitives.


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

**DFS — flat catalogue with single-character namespace tags.**
DFS does not have subdirectories. The on-disc catalogue is a flat
list of up to 31 entries (62 on Watford DDFS), each tagged with a
one-character "directory" — one of ``$``, ``A``–``Z``. The tags are
*siblings*, not parent-and-child: ``$.MYPROG`` and ``A.MYPROG`` are
two independent files; neither is "inside" the other. ``$`` is the
*default* directory that DFS assumes when a path omits one (per the
Acorn DFS User Guide), not a root that contains the others.

For this reason ``dfs.root`` is intentionally **not** a path for
``$``; it is the empty-string catalogue handle from which the ``/``
operator can build a path in *any* directory letter::

    dfs.root                       # the whole catalogue
    dfs.root / "$.HELLO"           # default directory
    dfs.root / "A.GAME"            # sibling directory A — not inside $

``DFSPath.mkdir()`` does not exist. ``^`` carries no meaning, since
there is no tree to walk up. ``iterdir()`` on the catalogue handle
yields one entry per populated directory letter; ``iterdir()`` on a
single-letter directory handle yields the files carrying that tag.

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

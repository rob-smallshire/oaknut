Paths and file specifications
=============================

``disc`` has three closely-related names for the things it points at,
all built from the same colon-joined grammar:

.. code-block:: text

   FILE_SPEC  =  IMAGE_SPEC  ":"  PATH_SPEC
            (compound-path = outer-path : inner-path)

- ``IMAGE_SPEC`` — also **outer-path** — a host-OS path to a disc image
  file (``games.ssd``, ``/var/discs/scsi0.dat``, ``C:\\Discs\\hd.dat``).
- ``PATH_SPEC`` — also **inner-path** — a path *inside* the image in
  whatever syntax that filesystem uses (``$.DIR.FILE`` on DFS / ADFS /
  AFS, ``Docs/Readme`` on a ZIP, ``afs:$.Library`` for the AFS partition
  on a combined disc). It may carry a partition selector.
- ``FILE_SPEC`` — also **compound-path** — the two joined with a colon:
  ``games.ssd:$.HELLO``. This is what most commands accept; the colon
  (and the inner-path after it) is optional when the command can default
  to the disc's root.

The ``outer-path`` / ``inner-path`` / ``compound-path`` names are the
project's preferred vocabulary going forward — clearer at a glance, no
commitment to Acorn-specific path syntax, and easier to disambiguate
when they appear as option values (e.g. ``disc for-each --mode
compound-path``). The ``IMAGE_SPEC`` / ``PATH_SPEC`` / ``FILE_SPEC``
forms remain in use across the older commands' help text and will be
swept across in a future pass.

Commands that operate on the disc as a whole (``disc create``,
``disc validate``, ``disc afs init``, …) take a plain outer-path
because an inner-path would be meaningless. Commands that operate
on a specific entry (``disc cat``, ``disc cp``, ``disc chmod``, …)
take a compound-path.


PATH_SPEC grammar
-----------------

In-image paths are written in Acorn syntax, not Unix syntax. The
component separator is ``.`` (a literal dot), not ``/``. A small set
of single-character names are reserved for directory references:

.. list-table::
   :header-rows: 1

   * - Symbol
     - Meaning
   * - ``$``
     - On ADFS and AFS, the root of the directory tree. On DFS, the
       *default* directory — see :ref:`dfs-flat-catalogue` below for
       why this matters.
   * - ``^``
     - The parent directory (one level up). Multiple hats chain
       (``^^`` is two levels up), and dots between consecutive
       hats are optional — ``^^`` and ``^.^`` are equivalent,
       matching Acorn ``*DIR`` syntax. Works on DFS too, where it
       walks up from a file to its single-character directory, and
       from there to the nameless root.
   * - ``@``
     - The current directory (rarely needed on the CLI — the *current*
       is always the filing system's notional root for batch tools)

A fully-qualified ADFS or AFS ``PATH_SPEC`` therefore starts with
``$.`` and walks down: ``$.Games.Elite`` is the file ``Elite`` inside
the directory ``Games`` at the root. Hats can appear mid-path to
sidestep up and across: ``$.Games.^.Docs.ReadMe`` walks down into
``Games``, back up one level to the root, and into ``Docs.ReadMe``
— useful as a single-string spelling of a file in a sibling
directory.

Filename component lengths vary by filing system: DFS allows up to 7
characters per filename (and exactly one character for the directory
prefix), while ADFS and AFS allow up to 10 characters per component
in a hierarchical tree. See :doc:`wildcards` for the matching rules
and length implications when patterns are involved.


.. _dfs-flat-catalogue:

DFS vs ADFS / AFS: flat catalogue vs hierarchical tree
------------------------------------------------------

Every filing system has a **root** — the implicit default for a
command whose ``PATH_SPEC`` is omitted. The three filing systems
differ in what their root is.

**ADFS and AFS — hierarchical trees.**
The root is ``$``. ``$.Games.Elite`` walks two levels down from
it: ``Games`` lives inside ``$``, and ``Elite`` lives inside
``Games``. Bare ``disc ls IMAGE.adl`` lists the children of
``$`` (subdirectories and files). Directory creation (``disc
mkdir``) and recursive operations (``disc cp -r``, ``disc tree``)
work the way Unix users would expect.

**DFS — single-character directories under a nameless root.**
A DFS catalogue holds up to 31 file entries (62 on Watford DFS).
Each lives in one of 27 directories — ``$`` and ``A``–``Z`` — and
all 27 are children of a nameless root. ``$`` is a sibling of
``A``–``Z``, not a container for them. ``$.MYPROG`` and
``A.MYPROG`` are two independent files. Empty directories cannot
exist — a directory comes into being the first time a file is
written under it and disappears again when its last file is
deleted, which is why ``disc mkdir`` is not a DFS operation.

Because the DFS root is nameless, there is no name to write in a
``PATH_SPEC``; the way to refer to the root is to omit the
``PATH_SPEC``. So bare ``disc ls IMAGE.ssd`` lists the populated
directory letters at the root, and the next level — the actual
files — is reachable via ``disc ls IMAGE.ssd:$`` (or ``:A``,
etc.).

What this looks like in practice:

.. code-block:: sh

   disc ls games.ssd                 # populated directory letters at
                                     # the (nameless) root
   disc ls 'games.ssd:$'             # files in directory $
   disc ls 'games.ssd:A'             # files in directory A
   disc cat 'games.ssd:$.HELLO'      # the file HELLO in directory $
   disc cat 'games.ssd:A.HELLO'      # the file HELLO in directory A —
                                     # different file from $.HELLO
   disc cat 'games.ssd:HELLO'        # error: PATH_SPEC needs a directory
                                     # letter; bare names do not resolve

No DFS command will recurse into siblings the way ADFS commands
recurse into subdirectories, because there are no subdirectories to
recurse into. ``disc mkdir`` is an ADFS-only command for the same
reason. ``disc tree`` does work on DFS images, but the resulting
"tree" is two levels deep at most: the catalogue, then each
populated directory letter.


Partition selectors
--------------------

A single disc image can hold more than one partition: an ADFS hard-disc
image, for instance, often carries an AFS partition in its tail
cylinders — the on-disc layout the Acorn Level 3 File Server uses,
sometimes called *AFS0* after the four-byte magic at the head of the
partition (see the :doc:`glossary </glossary>` for the longer note).
To address a particular partition, prefix the ``PATH_SPEC`` with the
partition's *filesystem key* and a colon:

.. cli-example:: partition_selectors
   :section: selectors

The selector is the registered filesystem key — ``acorn-dfs``,
``watford-dfs``, ``adfs``, ``afs``, … — the same vocabulary
``disc list-filesystems`` prints and ``--filesystem`` accepts. Keys are
lower-case, which is exactly what keeps a selector distinct from an
Acorn path (``$``, ``^`` and upper-case names never look like one). The
selector sits between the ``IMAGE_SPEC`` colon and the bare in-image
path. When an image holds two partitions of the same filesystem, the
first is the bare key and the rest are numbered from one: ``afs:`` is
the first AFS partition, ``afs.1:`` the second.

With no selector, ``disc`` identifies the image by its *content* — not
its file extension — and mounts the best candidate (the whole-image
host, so a combined ADFS+AFS disc opens at its ADFS root). Because
detection reads the bytes, an image whose extension is missing or wrong
still opens correctly.

If nothing recognises the image, the error lists what is installed:

.. cli-example:: partition_selectors
   :section: unrecognised

If you ask for a partition the image does not have, the error names the
ones it does:

.. cli-example:: partition_selectors
   :section: wrong_partition


Acorn star-aliases
------------------

Most ``disc`` subcommands have an Acorn-style alias prefixed with a
literal ``*`` so old muscle memory still works. The aliases route to
exactly the same implementations as their Unix-flavoured primary
names — they are not a separate command surface.

.. code-block:: sh

   disc '*CAT' games.ssd                # same as: disc ls games.ssd
   disc '*TYPE' 'games.ssd:$.HELLO'     # same as: disc cat …

Aliases must be quoted or escaped on POSIX shells because ``*`` is a
glob character — see :doc:`quoting` for the platform-specific forms.

.. list-table::
   :header-rows: 1

   * - Unix command
     - Acorn alias
   * - ``ls``
     - ``*CAT``
   * - ``cat``
     - ``*TYPE``
   * - ``rm``
     - ``*DELETE``
   * - ``mv``
     - ``*RENAME``
   * - ``cp``
     - ``*COPY``
   * - ``chmod``
     - ``*ACCESS``
   * - ``mkdir``
     - ``*CDIR``
   * - ``title``
     - ``*TITLE``
   * - ``opt``
     - ``*OPT4``
   * - ``stat``
     - ``*INFO``

``*LOAD`` and ``*SAVE`` are deliberately absent: on the original BBC
hardware they transferred bytes between memory and disc, which has no
clean analogue for a host-side tool. Use ``disc get`` / ``disc put``
instead.


Windows path handling
---------------------

A Windows-style absolute path such as ``C:\\Discs\\disc.dat`` contains
a colon — and so do ``FILE_SPEC``\ s. The parser disambiguates by
recognising the drive-letter prefix (a single ASCII letter followed
by ``:\`` or ``:/`` at the start of the spec) and skipping past it
before looking for the ``IMAGE_SPEC``/``PATH_SPEC`` colon. So
``C:\\Discs\\disc.dat:$.HELLO`` parses as the image
``C:\\Discs\\disc.dat`` plus the path ``$.HELLO``, never as the image
``C`` plus the path ``\\Discs\\disc.dat:$.HELLO``.

On POSIX shells the same backslash that Windows would write needs
quoting; see :doc:`quoting`.

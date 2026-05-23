Paths and file specifications
=============================

``disc`` has three closely-related names for the things it points at,
all built from the same colon-joined grammar:

.. code-block:: text

   FILE_SPEC  =  IMAGE_SPEC  ":"  PATH_SPEC

- ``IMAGE_SPEC`` — a host-OS path to a disc image file (``games.ssd``,
  ``/var/discs/scsi0.dat``, ``C:\\Discs\\hd.dat``).
- ``PATH_SPEC`` — an in-image Acorn path (``$.DIR.FILE``, ``^.SIB``,
  ``afs:$.Library``). It may carry a filing-system dispatch prefix.
- ``FILE_SPEC`` — the two joined with a colon: ``games.ssd:$.HELLO``.
  This is what most commands accept; the colon (and the ``PATH_SPEC``
  after it) is optional when the command can default to the disc's
  root.

Commands that operate on the disc as a whole (``disc create``,
``disc validate``, ``disc afs-init``, …) take a plain ``IMAGE_SPEC``
because a ``PATH_SPEC`` would be meaningless. Commands that operate
on a specific entry (``disc cat``, ``disc cp``, ``disc chmod``, …)
take a ``FILE_SPEC``.


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
     - The root directory of the filing system
   * - ``^``
     - The parent directory (one level up)
   * - ``@``
     - The current directory (rarely needed on the CLI — the *current*
       is always the filing system's notional root for batch tools)

A fully-qualified ``PATH_SPEC`` therefore starts with ``$.`` and walks
down: ``$.Games.Elite`` is the file ``Elite`` inside the directory
``Games`` at the root. ``^.Sib`` is the file ``Sib`` in the parent of
whatever directory the command's earlier argument named.

Filename component lengths vary by filing system: DFS allows up to 7
characters per filename (and exactly one character for the directory
prefix), while ADFS and AFS allow up to 10 characters per component
in a hierarchical tree. See :doc:`wildcards` for the matching rules
and length implications when patterns are involved.


Filing-system dispatch prefixes
-------------------------------

A single ADFS hard-disc image can carry an AFS partition in its tail
cylinders. To tell ``disc`` which filing system to address, prefix
the ``PATH_SPEC`` with a filing-system tag:

.. code-block:: sh

   disc ls scsi0.dat                       # default: ADFS root
   disc ls 'scsi0.dat:adfs:$'              # explicit ADFS
   disc ls 'scsi0.dat:afs:$'               # AFS partition root
   disc cat 'scsi0.dat:afs:$.Library.Free'

The three supported prefixes are ``dfs:``, ``adfs:``, and ``afs:``,
case-insensitive (``AFS:``, ``Afs:`` and ``afs:`` all work). The
prefix sits between the ``IMAGE_SPEC`` colon and the bare in-image
path, and is preserved through the parser so the routing decision
travels all the way to the filing-system handle.

When no prefix is given, the filing system is auto-detected from the
image filename:

.. list-table::
   :header-rows: 1

   * - Extension
     - Default filing system
   * - ``.ssd``, ``.dsd``
     - DFS
   * - ``.adf``, ``.adl``, ``.dat``
     - ADFS (which may then expose an AFS partition through ``afs:``)

If the extension is unrecognised, ``disc`` refuses to guess::

   $ disc ls some.image
   Error: cannot detect filing system from extension '.image'; use an
   explicit prefix (dfs:, adfs:, afs:)

If you ask for a filing system the image cannot provide, the error is
immediate and specific::

   $ disc ls 'games.ssd:adfs:$'
   Error: image is DFS format; cannot access as ADFS


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

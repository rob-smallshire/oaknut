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
``disc validate``, ``disc afs-init`` …) take a plain ``IMAGE_SPEC``
because a ``PATH_SPEC`` would be meaningless. Commands that operate
on a specific entry (``disc cat``, ``disc cp``, ``disc chmod`` …)
take a ``FILE_SPEC``.

.. note::

   This page is still being filled out. The sections below capture what
   was already documented; the gaps will be closed during the manual
   overhaul.

   Anticipated additions:

   - the ``PATH_SPEC`` grammar per filing system: ``$.DIR.FILE``
     (DFS, ADFS, AFS), ``^.SIBLING`` for the parent directory, leaf
     vs. fully-qualified forms
   - auto-detection of the filing system from the image extension
     and how to override it
   - quoting (covered in :doc:`quoting`) — the colon, ``$``, ``.``,
     and ``*`` characters all have shell meanings


Filing-system prefixes
----------------------

When a disc image carries multiple partitions (e.g. an ADFS hard disc
with an AFS tail partition), prefix the in-image path to select the
target partition:

.. code-block:: sh

   disc ls scsi0.dat                 # default: ADFS root
   disc ls 'scsi0.dat:adfs:$'        # explicit ADFS
   disc ls 'scsi0.dat:afs:$'         # AFS root
   disc cat 'scsi0.dat:afs:$.Library.Free'

The prefix is case-insensitive (``afs:``, ``AFS:``, ``Afs:`` all work).
When no prefix is given, the filing system is auto-detected from the
image extension (``.ssd``/``.dsd`` for DFS, ``.adf``/``.adl``/``.dat``
for ADFS).

Mismatches are rejected immediately::

   $ disc ls 'games.ssd:adfs:$'
   Error: image is DFS format; cannot access as ADFS


Acorn star-aliases
------------------

Acorn-style aliases are accepted alongside the Unix command names.
They must be quoted or escaped on POSIX shells because of the ``*``
prefix — see :doc:`quoting` for the platform-specific forms.

.. code-block:: sh

   disc '*CAT' games.ssd                # same as: disc ls games.ssd
   disc '*TYPE' 'games.ssd:$.HELLO'     # same as: disc cat 'games.ssd:$.HELLO'

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

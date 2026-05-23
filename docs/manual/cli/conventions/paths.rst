Paths and image specifications
==============================

Every ``disc`` command that touches an image takes an ``IMAGE_SPEC`` —
the path to the host file plus, optionally, an in-image path. The two
are joined with a colon: ``image.dat:$.DIR.FILE``.

.. note::

   This page is still being filled out. The sections below capture what
   was already documented; the gaps will be closed during the manual
   overhaul.

   Anticipated additions:

   - the canonical ``IMAGE:PATH`` syntax (will become the only
     supported form once the separate-arg form is removed)
   - in-image path grammar per filing system: ``$.DIR.FILE`` (DFS,
     ADFS, AFS), ``^.SIBLING`` for the parent directory
   - auto-detection of the filing system from the image extension
     and how to override it


Filing-system prefixes
----------------------

When a disc image carries multiple partitions (e.g. an ADFS hard disc
with an AFS tail partition), prefix the in-image path to select the
target partition:

.. code-block:: sh

   disc ls scsi0.dat              # default: ADFS root
   disc ls scsi0.dat adfs:'$'     # explicit ADFS
   disc ls scsi0.dat 'afs:$'      # AFS root
   disc cat scsi0.dat 'afs:$.Library.Free'

The prefix is case-insensitive (``afs:``, ``AFS:``, ``Afs:`` all work).
When no prefix is given, the filing system is auto-detected from the
image extension (``.ssd``/``.dsd`` for DFS, ``.adf``/``.adl``/``.dat``
for ADFS).

Mismatches are rejected immediately::

   $ disc ls games.ssd 'adfs:$'
   Error: image is DFS format; cannot access as ADFS


Acorn star-aliases
------------------

Acorn-style aliases are accepted alongside the Unix command names.
They must be quoted or escaped on POSIX shells because of the ``*``
prefix — see :doc:`quoting` for the platform-specific forms.

.. code-block:: sh

   disc '*CAT' games.ssd              # same as: disc ls games.ssd
   disc '*TYPE' games.ssd '$.HELLO'   # same as: disc cat

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

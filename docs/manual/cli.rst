The ``disc`` CLI
================

The ``disc`` command-line tool provides a unified interface for working
with Acorn DFS, ADFS, and AFS disc images. Install it with:

.. code-block:: sh

   uv add oaknut-disc

Both ``disc`` and ``oaknut-disc`` are registered as console scripts --
use whichever you prefer.


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
prefix:

.. code-block:: sh

   disc '*CAT' games.ssd       # same as: disc ls games.ssd
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


Cross-image copy
----------------

The ``cp`` command uses ``image:path`` colon syntax for copying files
between disc images of any format combination:

.. code-block:: sh

   disc cp source.ssd:'$.HELLO' target.dat:'$.HELLO'

Load and exec addresses are preserved. Access attributes are mapped
as losslessly as the target format allows (e.g. DFS only has a
locked bit, so public-read from ADFS is dropped).

For within-image copies, use the three-argument form:

.. code-block:: sh

   disc cp image.adl '$.Original' '$.Copy'


Creating a Level 3 File Server disc
------------------------------------

A complete walkthrough for building a bootable L3FS hard disc image:

.. code-block:: sh

   # Create a 10 MiB ADFS hard disc image
   disc create scsi0.dat --format adfs-hard --capacity 10MiB --title Server

   # Copy the file server binary from its DFS floppy
   disc cp FS3v126.ssd:'$.FS3v126' scsi0.dat:'$.FS3v126'

   # Create a !BOOT file and set the boot option
   printf '*RUN $.FS3v126\r' | disc put scsi0.dat '$.!BOOT' -
   disc opt scsi0.dat 3

   # Plan the AFS partition (shows geometry, free space, suggested command)
   disc afs-plan scsi0.dat

   # Initialise AFS with users and libraries
   disc afs-init scsi0.dat --disc-name Server --cylinders 309 \
     --user Syst:S --user RJS:2MiB \
     --emplace Library --emplace Library1

   # Inspect the result
   disc tree scsi0.dat

The ``--emplace`` option accepts either a shipped library name
(``Library``, ``Library1``, ``ArthurLib``) or a path to any ADFS
``.adl`` image. Everything in the image is copied into a directory
of the same name on the AFS partition.


Shell quoting
-------------

Acorn paths contain characters that POSIX shells interpret specially.
Use single quotes to prevent expansion:

- ``$`` -- shell variable prefix
- ``!`` -- zsh history expansion
- ``*`` -- glob character (for star-aliases)

.. code-block:: sh

   disc cat image.dat '$.!BOOT'     # single quotes: safe
   disc cat image.dat "$.!BOOT"     # double quotes: zsh expands !
   disc '\*CAT' image.dat           # backslash-escape the *

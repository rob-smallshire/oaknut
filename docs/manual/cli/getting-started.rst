Getting started
===============

The ``disc`` command-line tool speaks Acorn DFS, Acorn ADFS and AFS
transparently, with a subcommand-style interface (``disc ls``,
``disc cp``, ``disc afs-init``, etc.) supplemented by Acorn-style
star-command aliases — ``disc '*CAT'``, ``disc '*COPY'`` and so on.

This page walks from "I have a disc image" to "I am confident
reading and writing files" in about ten minutes. Every command
shown is runnable as-is — copy them into a shell. If you have not
yet installed ``oaknut-disc``, see :doc:`/install`. If you do not
have a real Acorn image handy, the :ref:`first-disc` section below
builds a blank one to follow along with.


First contact
-------------

Three commands cover the common case of "look at a disc and read a
file":

.. code-block:: sh

   disc ls     image.ssd                  # what's on this disc?
   disc tree   image.ssd                  # the same, recursive
   disc type   'image.ssd:$.README'       # read a text file to the terminal

If those work the way you expect, you already have enough of the
mental model to compose ``disc`` with normal shell tools. The rest of
this page fleshes out each step.

.. note::

   The Acorn-named alias for ``ls`` is ``*CAT`` — short for
   *catalogue*. ``disc cat`` is the Unix ``cat`` and dumps raw bytes
   to stdout; it is **not** an alias for the listing command. For
   reading a text file at a terminal, prefer ``disc type`` (used in
   the example above), which also translates Acorn line endings into
   the host's native form.


.. _first-disc:

Build a blank disc to follow along
----------------------------------

``disc create`` makes a fresh image you can write into. We will use a
single-sided BBC Micro floppy (SSD) — small, fast, and what most
Acorn-era disc images out in the wild are.

.. cli-example:: getting_started

The available ``--format`` values are ``ssd`` and ``dsd`` (DFS
floppies, single- and double-sided), ``adfs-s`` / ``adfs-m`` /
``adfs-l`` (ADFS floppies of the three standard sizes), and
``adfs-hard`` (ADFS hard discs — see :doc:`cookbook` for the
walkthrough that builds a Level 3 File Server disc).

The disc is empty but the catalogue and boot option are already in
place. Two sectors of the 800 total are "used" — sectors 0 and 1
hold the catalogue itself (the title, the boot option, and the file
index).


Put files in
------------

There are two ways to write into the disc.

**From a local file:**

.. code-block:: sh

   printf 'Welcome to the GETSTARTED disc.\r' > readme.txt
   disc put 'hello.ssd:$.README' readme.txt

**From standard input** (pipe a stream straight in):

.. code-block:: sh

   printf 'Welcome to the GETSTARTED disc.\r' | disc put 'hello.ssd:$.README' -

Both forms use ``printf`` rather than ``echo`` because BBC text files
terminate lines with ``\r`` (carriage return), not ``\n`` — and ``echo``
on every common shell appends ``\n``. ``disc put`` writes whatever
bytes it gets; the convention is yours to maintain. ``disc type``
later translates ``\r`` back to your host's native line ending when
reading the file out.

The trailing ``-`` in the stdin form is the long-standing Unix
idiom for "read this argument from stdin" — codified as a guideline
in POSIX's *Utility Conventions* and honoured by every ``disc``
write-command. See :doc:`conventions/quoting` for why the single
quotes around ``'hello.ssd:$.README'`` matter — the ``$`` would
otherwise be interpreted by your shell.

.. note::

   This example writes plain text. BBC BASIC programs *look* like
   text but are stored on disc as a binary tokenised form — keywords
   like ``PRINT`` and ``REM`` are single-byte tokens, not the
   characters of their names. Putting plain BASIC source bytes onto a
   disc with ``disc put`` makes a file that the BBC Micro will not
   execute. A future ``oaknut-basic`` CLI will tokenise / detokenise
   in both directions; for now, the bytes you put are the bytes you
   get back.


Read files out
--------------

Three commands depending on what you want:

.. code-block:: sh

   disc cat   'hello.ssd:$.README'        # raw bytes to stdout (no translation)
   disc type  'hello.ssd:$.README'        # translates Acorn CR -> host newlines
   disc get   'hello.ssd:$.README' out.txt  # copy to a host file, with metadata

- ``disc cat`` is the byte-faithful one — pipe it into ``hexdump`` if
  you want to look at the structure, or another command if you want
  to feed the bytes elsewhere.
- ``disc type`` is the read-this-on-a-modern-terminal one. It maps
  the Acorn ``\r`` line ending onto whatever your platform expects so
  the text reads cleanly without ``less`` or ``cat -v`` tricks.
- ``disc get`` writes the file to your host filesystem along with a
  metadata sidecar (an INF file by default) capturing the load /
  exec / access information that does not survive a plain host
  ``cp``. See :doc:`conventions/metadata` for the full menu of
  formats and when each is the right pick.


Browsing the catalogue
----------------------

The display you get from ``disc tree`` is a recursive view of every
entry on the disc. ``disc ls`` lists a single directory:

.. cli-example:: getting_started_browse

DFS files can sit under any of the single-character directories
``$`` (the root) and ``A`` through ``Z`` — pick whichever you like:

.. code-block:: sh

   disc ls 'hello.ssd:$.D'                # list the D directory

Both commands default to a human-readable display when stdout is a
terminal, and switch to a tab-separated, headers-on-the-first-line
output when piped or redirected (TSV). Override with ``--as
display|tsv|json`` — see :doc:`conventions/output-formats` for the
details.


A real Acorn disc: Repton Infinity
----------------------------------

Everything you just learned on the synthetic ``hello.ssd`` works
unchanged on a real Acorn-era disc. The project's test fixtures
include Superior Software's *Repton Infinity* (1988) — the game
plus its build-your-own-Repton editor suite plus the BBC Master
ROM images for the platform-specific build:

.. cli-example:: repton_infinity

Reading the output top to bottom:

- The disc's **boot option** is ``EXEC``. Pressing :kbd:`SHIFT-BREAK`
  on a real BBC effectively types ``*EXEC $.!BOOT``, which runs the
  contents of ``!BOOT`` as if each line had been typed at the OS
  prompt. The ``disc opt IMAGE`` command reads or sets the boot
  option.
- The catalogue contains the **game** (``MENU``, ``GAME``, ``GAME2``,
  ``REPTON``, ``Screen``), the **editor suite** (``MapEdit``,
  ``DefEdit``, ``SprEdit``, ``Linker``) — Repton Infinity was a
  build-your-own-Repton kit as much as a game — and the **sideways
  ROM images** ``MDROM4`` through ``MDROM7`` that the loader
  selects per host machine.
- ``!BOOT`` itself is just two lines of text:

  - ``*B.`` is the abbreviation for ``*BASIC``, the command that
    enters the BBC's built-in BASIC interpreter from the OS prompt.
  - ``CH."LOAD"`` is ``CHAIN "LOAD"``, BASIC for "load and run the
    program named ``LOAD``".

  So the full boot sequence on :kbd:`SHIFT-BREAK` is:
  ``*EXEC`` the boot file → ``*BASIC`` enters BASIC →
  ``CHAIN "LOAD"`` runs the program loader. Notice that ``disc
  type`` rendered the ``\r`` line endings correctly — Acorn text
  files use CR, modern terminals use LF, and ``type`` does the
  translation.
- The disc has **zero free sectors** — packed to the byte, which is
  what released DFS floppies of the era almost always were.


Acorn-style aliases
-------------------

If you have Acorn muscle memory, ``*CAT``, ``*INFO``, ``*RENAME``,
``*DELETE``, and friends all work as aliases for the Unix-named
commands. Quote or escape them at the shell level because ``*`` is
otherwise a glob:

.. code-block:: sh

   disc '*CAT'  hello.ssd                 # same as: disc ls hello.ssd
   disc '*INFO' hello.ssd                 # same as: disc stat
   disc '*TYPE' 'hello.ssd:$.README'      # same as: disc type

The full alias table is in :doc:`conventions/paths`.


A note on the other filing systems
----------------------------------

DFS images (``.ssd`` / ``.dsd``) have a flat catalogue with
single-character directories (``$`` and ``A`` — ``Z``) that do not
nest. ADFS images (``.adf`` / ``.adl`` / ``.dat``) and AFS
partitions on top of ADFS have hierarchical directories, so paths
nest naturally (``$.Games.Elite``).

On a disc that carries both ADFS *and* an AFS partition (most Level 3
File Server hard discs are like this), the ``afs:`` / ``adfs:``
dispatch prefix routes ``disc`` to the right partition::

   disc ls 'scsi0.dat'                    # default: the ADFS root
   disc ls 'scsi0.dat:adfs:$'             # explicit ADFS
   disc ls 'scsi0.dat:afs:$'              # the AFS partition root
   disc cat 'scsi0.dat:afs:$.Library.Free'

See :doc:`conventions/paths` for the full breakdown of
``FILE_SPEC = IMAGE_SPEC:PATH_SPEC``, dispatch prefixes, and
auto-detection rules.


When something fails
--------------------

Every ``disc`` failure produces exactly one ``Error: …`` line on
stderr and a non-zero exit code. The codes follow the BSD
``sysexits.h`` set — see :doc:`conventions/exit-codes` for the full
table.

For example, asking for a file that does not exist:

.. code-block:: sh

   $ disc cat 'hello.ssd:$.MISSING'
   Error: path not found: $.MISSING
   $ echo $?
   72

For debugging, ``disc --debug ...`` re-raises errors with a full
Python traceback so you can see exactly where they came from.


Where to go next
----------------

- :doc:`cookbook` — longer recipes that compose ``disc`` with shell
  scripting (cross-image copy, bulk-export to host, building a
  bootable L3FS hard disc).
- :doc:`commands/index` — the auto-generated reference for every
  subcommand, with full option listings.
- :doc:`conventions/index` — the single source of truth for path
  syntax, wildcards, shell quoting, output formats, and exit codes.
  Every command page links back here rather than restating these.
- :doc:`/api/cookbook` if you want to drive the same operations from
  Python code rather than the shell.

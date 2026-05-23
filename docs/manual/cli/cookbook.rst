CLI cookbook
============

Recipes that compose ``disc`` with shell tooling to solve real
end-to-end tasks. Each recipe is built around the Repton Infinity
disc image shipped in the project's test fixtures, so every command
shown is also runnable as-is against ``tests/data/images/games/``.

The output blocks below come from running the recipes at docs-build
time — they cannot drift from the actual binary's behaviour.


Finding files by pattern
------------------------

``disc find`` walks a disc's catalogue and returns the entries whose
path matches an Acorn wildcard pattern. The pattern lives in the
``PATH_SPEC`` half of the ``FILE_SPEC`` so it is quoted the same way
as any other in-image path:

.. cli-example:: find_pattern

The two patterns demonstrate the complementary shapes — ``*Edit``
finds every file *ending* in the literal text ``Edit`` (the
editor suite), and ``MDROM*`` finds every file *starting* with
``MDROM`` (the sideways ROM images). Matching is case-insensitive
and the ``*`` may appear anywhere in the pattern.

For the full wildcard grammar (including ``#`` for "any single
character") and the shell quoting that keeps the pattern out of the
shell's hands, see :doc:`conventions/wildcards`.


Bulk-export a disc to your host filesystem
------------------------------------------

``disc export`` lifts every file out of a disc image and into a
host directory tree, dropping an ``.inf`` sidecar next to each file
so the load / exec / length / attribute metadata survives the
crossing.

.. cli-example:: export_to_host

The ``.inf`` file is the *traditional* Acorn metadata format: one
line of five whitespace-separated fields — the Acorn filename, the
load address, the exec address, the length in bytes, and the access
byte. ``disc export`` defaults to ``--meta-format inf-trad``;
modern alternatives (``xattr-acorn``, ``filename-riscos``, etc.) are
documented in :doc:`/api/patterns/metadata`.

The resulting host tree round-trips back onto a disc with
``disc import``, preserving everything ``.inf`` captured. Inspect
or edit on the host using your normal tools, then push the changes
back.


Copying files across filing-system formats
------------------------------------------

``disc cp`` works between any combination of DFS, ADFS, and AFS
images. The source format does not have to match the destination
format — the CLI maps Acorn metadata across the formats for you:

.. cli-example:: cross_format_cp

Notice that the Repton ``MENU`` and ``REPTON`` files came from a
DFS catalogue (no per-file access bits, just a "locked" flag) and
arrived on an ADFS disc with the full ``WR/R`` access pair —
``disc cp`` filled in the defaults the source format could not
provide. Load and exec addresses survived intact, and the Acorn
case rule (case-preserving, case-insensitive) means renaming on
the way from ``$.MENU`` to ``$.Menu`` is a real change to how the
file displays, not a no-op.

The full attribute-mapping rules (which bits map across which
filesystems, and where information is lost in either direction) live
in :doc:`/api/patterns/metadata`.


Creating a Level 3 File Server disc
-----------------------------------

A complete walkthrough for building a bootable L3FS hard disc image.
This recipe needs the Acorn FS3 ROM binary, which is not shipped in
the test fixtures; once the user supplies one, the sequence below
runs end-to-end.

.. code-block:: sh

   # Create a 10 MiB ADFS hard disc image
   disc create scsi0.dat --format adfs-hard --capacity 10MiB --title Server

   # Copy the file server binary from its DFS floppy
   disc cp FS3v126.ssd:'$.FS3v126' scsi0.dat:'$.FS3v126'

   # Create a !BOOT file and set the boot option
   printf '*RUN $.FS3v126\r' | disc put 'scsi0.dat:$.!BOOT' -
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

.. note::

   When the FS3 ROM is added to the test corpus, this recipe will
   become a ``.. cli-example::`` block too — so the captured output
   matches the live behaviour the same way the other recipes on
   this page already do.

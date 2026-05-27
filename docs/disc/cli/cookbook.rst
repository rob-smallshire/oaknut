CLI cookbook
============

Recipes that compose ``disc`` with shell tooling for real
end-to-end tasks. Example data lives under
``tests/data/images/`` in the project's test fixtures, so every
recipe is runnable as-is.


Finding files by pattern
------------------------

To locate files by name, walk the catalogue with ``disc find``. The
pattern is an Acorn wildcard expression sitting in the ``PATH_SPEC``
half of the ``FILE_SPEC``, so it is quoted the same way as any other
in-image path:

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

To extract a whole disc to your host filesystem, use
``disc export``. Each file is written alongside an ``.inf`` sidecar
so the load / exec / length / attribute metadata survives the
crossing.

.. cli-example:: export_to_host

The ``.inf`` file is the *traditional* Acorn metadata format: one
line of five whitespace-separated fields — the Acorn filename, the
load address, the exec address, the length in bytes, and the access
byte. The default ``--meta-format inf-trad`` produces this form;
modern alternatives (``xattr-acorn``, ``filename-riscos``, etc.) are
documented in :doc:`/api/patterns/metadata`.

The host tree round-trips back onto a disc with ``disc import``,
preserving everything ``.inf`` captured. Inspect or edit on the host
using your normal tools, then push the changes back.


Copying files across filing-system formats
------------------------------------------

Copies span any combination of DFS, ADFS, and AFS images: source
and destination need not share a format because ``disc cp`` maps
Acorn metadata across them for you. (AFS here is the Acorn Level 3
File Server's partition format — sometimes called *AFS0* after the
magic at its head; see the :doc:`glossary </glossary>` for the
longer note.)

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


Browse a ZIP archive
--------------------

A ZIP archive is a filesystem too. ``disc`` recognises it by content
like any disc, and the same ``ls`` / ``tree`` / ``cat`` / ``get``
commands work against it — so a ZIP of RISC OS files is browsable
without unpacking it first.

.. cli-example:: browse_zip
   :section: identify

The archive here holds RISC OS files whose filetype is carried in the
``,xxx`` filename suffix. ``disc`` presents the flat ZIP namespace as a
directory tree — synthesising the ``Docs`` directory the archive only
implies — and decodes the suffix into the filetyped load address:

.. cli-example:: browse_zip
   :section: ls

.. cli-example:: browse_zip
   :section: tree

``disc get`` extracts a member to the host with its metadata sidecar, so
the filetype survives the trip out:

.. cli-example:: browse_zip
   :section: get

The mount is read-only: ``disc put`` / ``rm`` / ``mv`` into a ZIP are not
supported. The metadata recovery itself — SparkFS extras, bundled
``.inf`` sidecars, and filename encoding — belongs to the ``oaknut-zip``
package, which the ZIP filesystem wraps.


Archive a folder of SSDs to one ADFS hard disc
----------------------------------------------

You have a directory full of DFS ``.ssd`` floppies on your host
and want them all sitting on a single ADFS hard disc, each under
its own subdirectory named for the source.

Three lines of shell — a ``for`` loop wrapping a single
``disc cp -r`` per SSD — do the work.

**1. Create an empty archive disc.**

.. cli-example:: bulk_archive_ssds
   :section: create

A 10 MB ADFS hard-disc image is plenty for three DFS floppies-
worth of content; ``--title Games`` sets the name that ``*CAT``
will display.

**2. Look at the source filenames.**

.. cli-example:: bulk_archive_ssds
   :section: sources

Each SSD is named ``DiscNNN-Title.ssd`` — a disc-number prefix
followed by the game title. The loop in the next step pulls the
title's first word out of each filename and uses it as the
subdirectory name on the archive disc.

**3. Loop the SSDs, copying each into its own subdirectory.**

.. cli-example:: bulk_archive_ssds
   :section: loop

The interesting moves:

- The ``sed -E 's/.*-([A-Z][a-z]+).*/\1/'`` expression captures the
  first PascalCase word after the hyphen, yielding ``Planetoid`` /
  ``Arcadians`` / ``Zalaga``. Longer titles like
  ``PlanetoidAKADefender`` get truncated at the first uppercase
  letter, which fits comfortably inside ADFS's 10-character
  filename limit.
- ``disc cp -r SOURCE:$ TARGET:$.NAME`` recursively copies every
  file under the DFS directory ``$`` into ``$.NAME`` on the archive
  disc. The destination directory is **created automatically** —
  same convention as Unix ``cp -r SRC DEST`` when ``DEST`` does not
  exist. No explicit ``disc mkdir`` is required.
- The disc-side ``$`` characters appear as ``\$`` inside the
  double-quoted shell arguments: the arguments must be
  double-quoted (not single-quoted) so ``$ssd`` and ``$name``
  expand, and inside double quotes the shell would otherwise treat
  the bare ``$`` as the start of a variable name. Escaping with a
  backslash passes a literal ``$`` through to ``disc``. See
  :doc:`conventions/quoting` for the broader rules.

Note the silence: each successful ``disc cp -r`` writes nothing,
so the 18-file copy across three SSDs produces no stdout chatter.

**4. Verify the archive.**

.. cli-example:: bulk_archive_ssds
   :section: verify

The top level of the archive holds three sibling directories named
for the games — one per SSD. Walking the whole thing with
``disc tree`` then exposes each SSD's catalogue under the matching
directory.


Creating a Level 3 File Server disc
-----------------------------------

The full walkthrough builds a bootable L3FS hard disc from a fresh
ADFS envelope plus the file-server executable shipped on
``tests/data/images/cookbook/FS3v126.ssd``.

**1. Lay down an empty ADFS hard-disc envelope.**

.. cli-example:: l3fs_disc
   :section: envelope

Here ``disc create`` reserves the file on the host and writes the
ADFS catalogue + free-space map. The ``.dat`` extension selects ADFS;
``--geometry capacity=10MB`` sizes the hard disc (``disc`` derives a
cylinders/heads/sectors layout for that capacity); and ``--title``
sets the on-disc title that ``*CAT`` will display.

The command is silent on success — see :doc:`conventions/exit-codes`
for the broader contract.

**2. Install the file-server binary onto the new disc.**

.. cli-example:: l3fs_disc
   :section: install_fs

A classic cross-format ``disc cp`` — the source ``$.FS3v126`` lives
on a DFS floppy, the destination is the same name on the ADFS
partition of the hard disc we just created. Load and exec
addresses survive the crossing; see :doc:`/api/patterns/metadata`
for the attribute-mapping table.

**3. Write a !BOOT command file and turn on autoboot.**

.. cli-example:: l3fs_disc
   :section: boot

The ``!BOOT`` command file, which will be ``*EXEC``-uted at boot,
contains ``*RUN $.FS3v126\r`` — the ``*RUN`` invocation plus the
Acorn carriage-return line ending — so that loading the disc
launches the file-server executable. Here ``printf`` builds those
bytes on stdout, the shell pipes them in, and the trailing ``-``
tells ``disc put`` to read from stdin (the standard Unix
convention). We use ``printf`` rather than ``echo`` because ``echo``
appends ``\n`` on every common shell, and we need ``\r`` — see
:doc:`getting-started` for the line-ending rationale.

With no value, ``disc opt scsi0.dat`` reads the current boot option
(``0`` / ``OFF`` on a freshly-created disc); passing ``EXEC`` sets
it. Symbolic names (``OFF`` / ``LOAD`` / ``RUN`` / ``EXEC``) are
accepted alongside the numeric forms (``0`` / ``1`` / ``2`` /
``3``); ``disc opt --help`` lists the full mapping.

``EXEC`` is the right choice here because ``!BOOT`` is a command
file, not a binary — pressing :kbd:`SHIFT-BREAK` runs
``*EXEC $.!BOOT``, which effectively types the ``*RUN $.FS3v126``
line at the OS prompt.

**4. Plan the AFS partition (optional).**

.. cli-example:: l3fs_disc
   :section: plan_afs

The ``afs plan`` command is a dry-run that shows the disc's geometry,
how many sectors ADFS currently occupies, and what an AFS partition built
from the remaining free space would look like. Nothing is written
— the step is there to let you review the proposed shape before
committing. Skip it if you know what you want.

**5. Initialise the AFS partition.**

.. cli-example:: l3fs_disc
   :section: init_afs

The ``afs init`` command carves out the AFS partition for real, adds
an ``RJS`` regular user, omits the provided-by-default ``Welcome``
account, and emplaces two shipped library images.

Note the absence of ``--cylinders``: when omitted, ``afs init``
claims the existing free space, which is exactly what ``afs plan``
suggested. Pass an explicit value if you want a smaller AFS region
and ADFS retained beyond what is strictly necessary.

The ``--emplace`` option accepts a shipped name (``Library``,
``Library1``, ``ArthurLib``) or a path to any ADFS ``.adl``; the
contents land in a directory of the same name on the AFS partition.

**6. Inspect the new AFS partition.**

.. cli-example:: l3fs_disc
   :section: inspect_afs

The ``disc afs users`` command confirms the resulting account list:
``Syst``, ``Boot``, and ``RJS`` are present; ``Welcome`` is not. The
``Syst`` and ``Boot`` accounts are not created explicitly — they
are built-ins and arrive for free with every freshly-initialised
AFS partition (``Welcome`` would too, but for the explicit
omission). To change a built-in's quota instead of dropping it,
supply ``--user NAME:QUOTA`` and the spec overrides the default.

No account has a password unless you ask for one — a freshly
initialised disc leaves even the system account ``Syst`` open. The
Level 3 File Server stores passwords as up to six cleartext ASCII
characters (there is no encryption), so the only thing guarding the
file on a real disc is its hidden access byte. Passwords live outside
the ``--user`` spec — a password may itself contain a colon, which the
colon-delimited spec could not represent — and are set with their own
``--user-password NAME=VALUE`` option, split once on the first ``=``.
To ship the disc with the system account already protected, add it at
initialisation::

    disc afs init scsi0.dat --disc-name Server --user-password Syst=secret

``NAME`` matches a ``--user`` or a built-in; set a password later with
``disc afs passwd IMAGE NAME --password VALUE``.

**7. Verify the dual-partition shape and walk the disc.**

.. cli-example:: l3fs_disc
   :section: verify

The ``stat`` report confirms the three-block layout — a ``Disc``
envelope carrying the physical geometry, then ``Partition 1: ADFS``
holding the boot configuration and the FS binary, then
``Partition 2: AFS`` ready to serve files over Econet. The
single-partition collapsed form documented in
:doc:`conventions/output-formats` does not apply here because the
two partitions genuinely carry different things; the envelope is
the natural umbrella.

Walking the whole image with ``disc tree`` then exposes both
halves. The ADFS half is tiny — just ``!BOOT`` and the FS3 binary,
which is all the boot needs to load before handing off to AFS.

The AFS half shows the two emplaced library trees in full, with
the BBC-era utilities (``LCAT``, ``NETMON``, ``PROT``, ``USERS``,
…) that the Level 3 File Server's clients reach for via
``*<command>`` once the server is up.

CLI cookbook
============

Recipes that compose ``disc`` with shell tooling for real
end-to-end tasks. Example data lives under
``tests/data/images/`` in the project's test fixtures, so every
recipe is runnable as-is.


Finding files by pattern
------------------------

To locate files by name, walk the catalogue with ``disc find``. The
pattern is an Acorn wildcard expression sitting in the ``INNER_PATH``
half of the ``COMPOUND_PATH``, so it is quoted the same way as any other
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


Assemble a double-sided DSD from two SSDs
-----------------------------------------

A double-sided disc holds **two independent DFS volumes** — Acorn
drives ``:0`` and ``:2`` — one per physical surface. To combine two
single-sided ``.ssd`` floppies onto one ``.dsd``, create a blank
double-sided image and copy one SSD onto each side. The second side
is addressed with verbatim Acorn drive syntax: ``image::2.$``.

**1. The two source SSDs.**

.. cli-example:: assemble_dsd_from_ssds
   :section: sources

Two single-sided game floppies — Arcadians and Zalaga — each with a
handful of files under ``$``.

**2. Create a blank double-sided disc.**

.. cli-example:: assemble_dsd_from_ssds
   :section: create

``disc create`` with a ``.dsd`` extension lays down an 80-track
double-sided image and formats **both** sides as empty catalogues, so
each side is a usable volume from the outset. No ``--title`` here — both
sides start blank and are named symmetrically further down.

**3. Copy one SSD onto each side.**

.. cli-example:: assemble_dsd_from_ssds
   :section: copy

The moves:

- Each side is addressed explicitly: ``compendium.dsd::0.…`` is **drive
  0**, ``compendium.dsd::2.…`` is **drive 2**. The two colons are the
  CLI's image delimiter followed by the Acorn drive colon, preserved
  verbatim; ``:0`` / ``:2`` is the drive, ``$`` the directory.
- ``$.*`` globs every file in the source's ``$`` directory. The trailing
  ``.`` on the destination — ``$.`` — is the **Acorn directory marker**:
  "copy into the ``$`` directory". It plays the role Unix ``cp`` gives a
  trailing ``/``, but keeps the path native Acorn. (``/`` is still
  accepted if you prefer it.) The marker matters because an empty DFS
  side has no ``$`` entry yet, so the destination directory has to be
  named as such rather than detected.

Each side is an independent volume with its own title, set after the
copy. Addressing a side's **disc title** takes the drive with **no
path** — ``compendium.dsd::0`` / ``compendium.dsd::2``. (``::2.$`` would
instead ask for the ``$`` *directory's* title, which DFS has no concept
of.) There are two ways to supply the name, shown in turn.

**4. Name side 0 directly.**

.. cli-example:: assemble_dsd_from_ssds
   :section: title-direct

The straightforward way: type the title. A DFS title holds up to 12
characters, so ``Arcadians`` (nine) fits with room to spare.

**5. Name side 2 from its source.**

.. cli-example:: assemble_dsd_from_ssds
   :section: title-carry

When the source floppy is already named the way you want, read the title
straight off it rather than retyping. The inner ```disc title
zalaga.ssd``` prints the source's disc title; the outer ``disc title``
writes it onto side 2 — a command substitution carrying the name across.

**6. Verify both sides.**

.. cli-example:: assemble_dsd_from_ssds
   :section: verify

``disc stat`` lists the disc as two volumes, each under the
designation that addresses it — **Drive :0** and **Drive :2** — with
its own title, file count and free space. Listing each side then shows
the game that now lives there.


Split a double-sided DSD into two SSDs
--------------------------------------

The reverse: lift each side of a ``.dsd`` out into its own
single-sided ``.ssd``. Each side is an independent volume, so this is
just two copies — one per side — into two freshly-created SSDs.

**1. The two-sided source disc.**

.. cli-example:: split_dsd_into_ssds
   :section: source

``disc stat`` shows the DSD as two volumes, Drive ``:0`` and Drive
``:2``, each a full DFS catalogue.

**2. Create the two destination SSDs.**

.. cli-example:: split_dsd_into_ssds
   :section: create

**3. Copy each side out to its own SSD.**

.. cli-example:: split_dsd_into_ssds
   :section: extract

Each side is addressed explicitly — ``compendium.dsd::0.…`` and
``compendium.dsd::2.…``. The ``$.*`` glob lifts every file out of each
side's ``$`` directory into the target SSD, whose own ``$.`` names the
destination directory.

**4. Verify each extracted SSD.**

.. cli-example:: split_dsd_into_ssds
   :section: verify

Each single-sided image now holds exactly one side's catalogue — the
DSD has been separated back into the two floppies it was assembled
from.


Consolidate Acorn DFS discs onto a higher-capacity Watford DFS disc
-------------------------------------------------------------------

Acorn DFS caps a disc at **31 files**; Watford DFS extends the
catalogue to **62 files per side**. That difference is the whole point
of this recipe. Daily telemetry — one file per day — fills an Acorn
disc in a month (up to 31 days), so four months of 1984 temperature
readings for Cambridge sit on four separate single-sided Acorn
floppies. A single double-sided Watford disc swallows all four: two
months a side. It is also a copy from one DFS variant to another.

**1. The four monthly Acorn discs.**

.. cli-example:: consolidate_telemetry
   :section: inputs

Each ``.ssd`` is one month, holding files named ``84MMDD`` — a day's 24
hourly temperatures in degrees Celsius, carriage-return separated (the
Acorn line ending). January's catalogue holds 31 files: Acorn's ceiling,
hit exactly.

**2. Create a blank Watford disc.**

.. cli-example:: consolidate_telemetry
   :section: create

``--filesystem watford-dfs`` is required: ``disc create`` infers Acorn
DFS from the ``.dsd`` extension, so the Watford variant must be named
explicitly. The double-sided geometry gives two 62-file catalogues.

**3. Copy two months onto each side.**

.. cli-example:: consolidate_telemetry
   :section: copy

Side 0 takes January and February, side 2 March and April —
``telem.dsd::0.$.`` and ``telem.dsd::2.$.``. Each ``disc cp`` reads an
Acorn catalogue and writes a Watford one; the file data and load/exec
addresses carry across unchanged.

**4. Name each side.**

.. cli-example:: consolidate_telemetry
   :section: title

A Watford title is 10 characters (two fewer than Acorn's 12), so
``Jan-Feb 84`` and ``Mar-Apr 84`` fit exactly.

**5. Verify the consolidation.**

.. cli-example:: consolidate_telemetry
   :section: verify

Side 0 carries 60 files (31 + 29 — 1984 was a leap year) and side 2
carries 61 (31 + 30). Both are well past the 31 a single Acorn disc
could hold, which is exactly why the four discs became one.


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
bytes on stdout, the shell pipes them in, and the trailing hyphen
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


A checksum table for every file on a disc
-----------------------------------------

To pair every in-image path with a checksum of its bytes — to verify
a transfer, compare two copies, or spot-check a build — ``disc
for-each`` writes the table in one command. The default
``--mode content`` pipes each file's bytes to the command; the
command's stdout becomes that file's row. When stdout is captured,
``disc`` writes TSV:

.. code-block:: sh

   disc for-each 'image.ssd:*' -- <command> > checksums.tsv

Three choices for ``<command>``.

A CRC32 from ``cksum``
~~~~~~~~~~~~~~~~~~~~~~

On stdin, ``cksum`` emits ``<crc32> <bytes>``:

.. cli-example:: checksum_each_file
   :section: cksum

CRC32 is a compact fingerprint, fine for spotting differences between
two copies of a file. It's also computable on the BBC Micro itself.

An MD5 from ``md5sum``
~~~~~~~~~~~~~~~~~~~~~~

``md5sum`` (GNU coreutils) gives a longer fingerprint — a
32-character hex digest that downstream tooling and published
archives commonly cite:

.. cli-example:: checksum_each_file
   :section: md5sum

The trailing ``  -`` is ``md5sum``'s standard marker for input read
from stdin.

Trimming the marker
~~~~~~~~~~~~~~~~~~~

For a clean ``<path>\t<hash>`` table, strip the ``  -`` from the
stream:

.. cli-example:: checksum_each_file
   :section: md5sum-trim

The for-each output is text; the rest of the shell's text tools work
normally — ``awk`` to rename columns, ``sort`` for ordering, ``grep
-v`` to drop rows by pattern.


Files containing a string
-------------------------

To find every file on a disc whose bytes contain a string — here, the
BBC BASIC keyword ``PROC`` — pair ``disc for-each`` with ``grep -c``.
The match count for each file becomes the output column:

.. cli-example:: grep_each_file
   :section: count

For just the paths of the files that matched, strip the header with
``--no-header`` and filter on the count column:

.. cli-example:: grep_each_file
   :section: paths


Create a game cartridge ROM
---------------------------

ROMFS is the paged-ROM filing system of the BBC Micro and Acorn
Electron — a sideways ROM or cartridge. ``disc create`` makes one (the
``.rom`` extension infers ROMFS), and the ``disc romfs`` commands query
and set its paged-ROM header properties.

Here we put the BBC Micro game *Snapper* (Acornsoft, 1982) onto a
cartridge: create a fresh 16 KiB ROM with a title and the publisher's
copyright, then copy the whole game off its DFS floppy with ``disc cp``,
which carries each file's load and execution addresses across.

.. cli-example:: game_cartridge

The cartridge responds to ``*HELP`` with its title. To use it, switch to
the ROM filing system with ``*ROM`` and then use the ordinary filing-system
commands — ``*CAT`` to list the files, ``*EXEC !BOOT`` to start Snapper,
and ``*RUN`` / ``*LOAD`` / ``CHAIN`` as usual. (This cartridge has been
built and run from ROM in a 6502 emulator.)

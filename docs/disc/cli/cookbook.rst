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


Files whose names contain wildcard characters
---------------------------------------------

A filename can contain ``*`` or ``#`` — the very characters that are
wildcards at the command line. The game Guardian, for instance, ships
``guard#1`` and ``guard#2`` on its disc. ``disc`` stores and addresses
these names faithfully.

**1. Create the wildcard-named files.**

Writing them is unremarkable — quote the path so the shell leaves the
``#`` and ``$`` alone, and ``disc put`` stores the name verbatim:

.. cli-example:: wildcard_literal_names
   :section: create

The disc already held ``guard41`` and ``guard42``; now it carries
``guard#1`` and ``guard#2`` too.

**2. Copy the whole disc, wildcard names and all.**

A bulk copy treats the ``#`` files like any other — the wildcard in
``$.*`` is on the *source* side and matches every entry, so the lot
lands on a fresh blank SSD:

.. cli-example:: wildcard_literal_names
   :section: copy

**3. The trap: retrieving one of them by name.**

Now the ``#`` bites. As a pattern, ``guard#1`` means "``guard``, any
one character, ``1``" — which matches both ``guard#1`` *and*
``guard41``, so a plain copy quietly picks up the neighbour:

.. cli-example:: wildcard_literal_names
   :section: decoy

**4. The fix: --no-wildcards.**

``--no-wildcards`` turns off pattern interpretation for that one
command, so ``guard#1`` addresses exactly the file with the ``#`` in
it and the ``guard41`` decoy is left behind:

.. cli-example:: wildcard_literal_names
   :section: literal

The same flag is available on every selecting command — ``cp``,
``rm``, ``chmod``, ``lock``, ``unlock``, ``set-load``, ``set-exec`` —
whenever a literal ``*`` or ``#`` in a name would otherwise be read as
a wildcard. Extracting a single file to the host with ``disc get``
needs no flag at all: it addresses its path literally, never as a
pattern. The full wildcard grammar and the ``--no-wildcards`` opt-out
are covered in :doc:`conventions/wildcards`.


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
implies — and, because the files are RISC OS types, decodes the suffix
into a *Filetype* column rather than showing the raw filetyped load
address (its ``type-date`` lens; pass ``--metadata-lens=addresses`` to
see the encoding instead):

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


.. _gather-many-discs:

Build a Pi1MHz / BeebSCSI hard disc from a shelf of cover discs
---------------------------------------------------------------

You have a directory full of floppy images — DFS ``.ssd``/``.dsd``
and ADFS ``.adf``/``.adl`` in any mix — and want them all on one
hard disc, each under its own directory, ready to serve from a
`Pi1MHz <https://github.com/dp111/Pi1MHz>`_ (or standalone BeebSCSI)
as a single virtual drive on a real BBC Micro.

``disc gather`` does the collation in one command: it copies each
source image's files into its own directory of the destination,
naming the directory from the host filename by default (or the
disc's on-disc title with ``--name-from title``), sanitising the
name to the destination filesystem's rules and de-duplicating
collisions. The destination is opened once for the whole run and
must be a hierarchical image (ADFS or AFS — a flat DFS destination
is refused). The same operation is available from Python as
``oaknut.disc.gather(destination, sources, …)``, so a batch import
needs no shell at all — handy on Windows.

BeebSCSI keeps each virtual drive ("LUN") on its SD card as
``BeebSCSI<n>/scsiN.dat`` — a raw ADFS image, precisely what
``disc create`` writes — beside a geometry sidecar. So the whole job
is three moves: create the LUN image with its sidecar, gather the
cover discs onto it, and drop it into the card's ``BeebSCSI0``
directory.

**1. Create the LUN image with its sidecar.**

.. cli-example:: pi1mhz_beebscsi
   :section: create

Naming the image ``scsi0.dat`` from the outset means its sidecar
comes out as ``scsi0.cfg`` — the name BeebSCSI reads for LUN 0.
``--sidecar cfg`` writes the ``.cfg`` alongside, carrying the disc
geometry BeebSCSI needs.

**2. Gather the cover discs onto it.**

.. cli-example:: pi1mhz_beebscsi
   :section: gather

One command copies all four discs — three DFS ``.ssd`` and one ADFS
``.adl`` — each into a directory named for its file, cross-format
metadata mapped exactly as ``disc cp`` does. The report shows where
each landed; names are sanitised to ADFS's ten-character limit and
de-duplicated. Here the filenames are already tidy; when a disc's
own title would read better, add ``--name-from title``.

**3. See the assembled collection.**

.. cli-example:: pi1mhz_beebscsi
   :section: tree

Each cover disc is now a sibling directory at the root. ``--depth 1``
keeps the view to the top level; the ellipsis under each directory
marks the files the gather step copied in.

**4. Lay the LUN out for the SD card.**

.. cli-example:: pi1mhz_beebscsi
   :section: deploy

BeebSCSI reads LUN 0 of the first drive from ``BeebSCSI0/scsi0.dat``
(plus ``scsi0.cfg``), so the whole deployment is copying the image
and its sidecar into that directory on the card. Further LUNs are
``scsi1.dat``, ``scsi2.dat``, … in the same directory; a second
BeebSCSI directory (``BeebSCSI1/``) holds the next four drives.
Copy the ``BeebSCSI0`` directory to the root of a FAT-formatted SD
card and the collection is ready to mount from the BBC.


Gathering with custom directory names
-------------------------------------

``disc gather`` names each directory from the source filename or its
disc title. When you need a name neither gives you — a title's
*first word*, say, or a value from a manifest — drop to a shell
``for`` loop around ``disc cp -r``, which puts the full expressive
power of the shell behind the naming:

.. cli-example:: bulk_archive_ssds
   :section: loop

The moves:

- The ``sed -E 's/.*-([A-Z][a-z]+).*/\1/'`` expression captures the
  first PascalCase word after the hyphen, yielding ``Planetoid`` /
  ``Arcadians`` / ``Zalaga``, well inside ADFS's 10-character limit.
- ``disc cp -r SOURCE:$ TARGET:$.NAME`` recursively copies every
  file under the source's ``$`` into ``$.NAME`` on the destination,
  which is **created automatically** — no ``disc mkdir`` needed.
- The disc-side ``$`` appears as ``\$`` inside the double-quoted
  shell arguments, so ``$ssd``/``$name`` expand while the literal
  ``$`` passes through to ``disc``. See :doc:`conventions/quoting`.


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

This recipe builds a hard disc that boots straight into a running Level
3 File Server. It uses version 1.26: download ``l3v126.ssd`` from the
`mmbeeb/L3V126 release
<https://github.com/mmbeeb/L3V126/releases/tag/MML3V126>`_. The
executable on that disc is ``$.FS``; the recipe installs it as
``$.FS3v126``, the name conventionally given to the 1.26 server.

**1. Create an empty ADFS hard disc.**

.. cli-example:: l3fs_disc
   :section: envelope

The ``.dat`` extension selects ADFS, and ``--geometry capacity=10MB``
sizes the disc.

**2. Install the file server.**

.. cli-example:: l3fs_disc
   :section: install_fs

The copy from the DFS floppy preserves the load and exec addresses.

**3. Add a start-up program that answers the server's questions.**

On start-up the file server asks for the ``Number of drives:``, a
``Command :`` (``S`` to start, with no :kbd:`RETURN`), and the number
of ``Stations:``. This BASIC program places the answers in the keyboard
buffer, then runs the server:

.. literalinclude:: ../../../scripts/cli-examples/sources/StartFS.bas
   :language: bbcbasic
   :caption: StartFS.bas

Line 80 defines soft key 0 as the answers, with ``|M`` for
:kbd:`RETURN`. Line 90, ``*FX138,0,128``, inserts soft key 0's code
into the keyboard buffer, so the server reads the answers as if
:kbd:`f0` had been pressed. Line 100 runs the server (``*/`` is short
for ``*RUN``). The date comes from the real-time clock dongle the
server checks for, which doubles as its copy protection. Line 70 guards
against running without the 6502 Second Processor the server requires.

Tokenise the program onto the disc with the addresses a saved BASIC
program carries:

.. cli-example:: l3fs_disc
   :section: startup

**4. Chain the start-up program at boot.**

.. cli-example:: l3fs_disc
   :section: boot

The ``!BOOT`` file holds ``CHAIN"StartFS"`` with an Acorn ``\r`` line
ending, which is why the recipe uses ``printf`` rather than ``echo``.
Boot option ``EXEC`` makes :kbd:`SHIFT-BREAK` ``*EXEC`` it. Avoid
starting ``!BOOT`` with ``*ADFS``: changing filing system closes the
``*EXEC`` file before the ``CHAIN`` is read.

**5. Plan the AFS partition (optional).**

.. cli-example:: l3fs_disc
   :section: plan_afs

This dry run shows the AFS partition that the free space after ADFS
would hold. Nothing is written.

**6. Initialise the AFS partition.**

.. cli-example:: l3fs_disc
   :section: init_afs

The ``afs init`` command claims the free space ``afs plan`` proposed
(pass ``--cylinders`` for less), adds user ``RJS``, drops the built-in
``Welcome`` account, and emplaces two shipped libraries. The
``--emplace`` option also accepts the path to any ADFS ``.adl``.

**7. Check the accounts.**

.. cli-example:: l3fs_disc
   :section: inspect_afs

The ``Syst`` and ``Boot`` accounts are built in. No account has a password
until you set one, with ``--user-password NAME=VALUE`` on ``afs init``
or later with ``disc afs passwd``.

**8. Copy files into the AFS partition.**

.. cli-example:: l3fs_disc
   :section: populate_afs

The ``afs:`` selector addresses the AFS partition, and ``disc cp``
creates ``Saves`` on the way. Files from DFS arrive owner-only
(``WR/``), so anything other users run, such as a library command,
needs ``--access R/R`` or a later ``disc chmod``.

**9. Verify the disc.**

.. cli-example:: l3fs_disc
   :section: verify

The ADFS partition holds just the boot files; the AFS partition holds
the users' directories and the libraries the server's clients use.


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


Store host BASIC source on a disc as a tokenised program
--------------------------------------------------------

A BBC Micro keeps a BASIC program on disc in *tokenised* form — keywords
packed to single bytes, each line framed by an ``&0D`` marker — not as the
source text you type at the keyboard. The ``oaknut-basic`` tool converts
between the two halves of that divide, and it reads stdin / writes stdout
by default, so it stands either side of ``disc`` in a pipe.

**1. The host source.**

A plain, numbered ``.bas`` text file authored in any editor:

.. cli-example:: basic_text_roundtrip
   :section: author

**2. Tokenise it onto the disc.**

One pipe tokenises the source and stores the program bytes. ``disc put``
reads its data from stdin when no host path is given, so the pipe needs no
trailing ``-``:

.. cli-example:: basic_text_roundtrip
   :section: put

The ``--load 0x1900`` / ``--exec 0x8023`` stamp the addresses a BASIC
program carries on disc — ``PAGE`` and the BASIC ROM's entry — so the
stored ``GREET`` is ready to ``CHAIN``. The catalogue confirms the 69-byte
tokenised program landed with those addresses.

**3. Lift it back out to a host text file.**

The reverse direction streams the stored program through the
de-tokeniser. ``disc cat`` writes the file's raw bytes to stdout, which
``oaknut-basic detokenise`` turns back into numbered source:

.. cli-example:: basic_text_roundtrip
   :section: get

The recovered listing is identical to the source it started from — the
round trip is lossless.


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
and ``*RUN`` / ``*LOAD`` / ``CHAIN`` as usual.

Loaded into a BBC Micro (here, an emulator), a session looks like this:

.. code-block:: text

   BBC Computer 32K

   BASIC

   >*HELP

   Snapper

   OS 1.20
   >*ROM
   >*CAT

   *Snapper*
   Snappe3
   Snap2
   SNAPPER
   SNAP
   !BOOT
   >*EXEC !BOOT


Control storage order to manage seek times
------------------------------------------

A floppy drive — and an emulator faithful to one — seeks from file to
file as they are read, so the order files lie in on the disc decides how
much the head travels. The fast arrangement keeps the files read first —
a boot file, a loader, opening data — in the low-numbered sectors, where
the head starts out.

The ``disc storage-order`` command reports this physical order — the
files in the order they lie on the disc, from the lowest sector up:

.. cli-example:: storage_order_seek_times

Here a big 10K file sits in the lowest sectors, so reaching ``!BOOT``
means seeking across the whole disc before loading can even begin.
``disc compact --order`` rewrites the layout, laying the named files down
first, in the lowest sectors; every file it does not name follows in its
existing physical order. The list is a prefix, so naming ``!BOOT`` and
the loader is enough to bring them to the front and leave the rest where
they are. The second ``disc storage-order`` confirms the result.

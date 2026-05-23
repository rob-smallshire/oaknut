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

The full walkthrough builds a bootable L3FS hard disc from a fresh
ADFS envelope plus the file-server executable shipped on
``tests/data/images/cookbook/FS3v126.ssd``. The recipe runs as one
coherent sequence — the same image is carried forward from step to
step — but the captured transcript is sliced into named sections so
each step's output can sit next to its own explanation.

**1. Lay down an empty ADFS hard-disc envelope.**

.. cli-example:: l3fs_disc
   :section: envelope

``disc create`` reserves the file on the host and writes the ADFS
catalogue + free-space map. ``--format adfs-hard`` picks the
hard-disc geometry family; ``--capacity 10MB`` sizes it; ``--title``
sets the on-disc title that ``*CAT`` will display. The command is
silent on success — see :doc:`conventions/exit-codes` for the
broader contract.

**2. Install the file-server binary onto the new disc.**

.. cli-example:: l3fs_disc
   :section: install_fs

A classic cross-format ``disc cp`` — the source ``$.FS3v126`` lives
on a DFS floppy, the destination is the same name on the ADFS
partition of the hard disc we just created. Load and exec
addresses survive the crossing; see :doc:`/api/patterns/metadata`
for the attribute-mapping table.

**3. Write a ``!BOOT`` command file and turn on autoboot.**

.. cli-example:: l3fs_disc
   :section: boot

``disc put`` writes a one-line ``!BOOT`` whose contents are
``*RUN $.FS3v126`` followed by the Acorn ``\r`` line ending.
``printf`` builds those bytes on stdout, the shell pipes them into
``disc put``, and the trailing ``-`` is the long-standing Unix
idiom for "read this argument from stdin" — codified as a guideline
in POSIX's *Utility Conventions* and inherited unchanged here. The
``printf`` rather than ``echo`` choice is forced by the ``\r`` —
see :doc:`getting-started` for the line-ending rationale.

``disc opt scsi0.dat`` with no value reads the current boot option
(``0`` / ``OFF`` on a freshly-created disc) and ``disc opt
scsi0.dat EXEC`` sets it. Symbolic names (``OFF`` / ``LOAD`` /
``RUN`` / ``EXEC``) are accepted alongside the numeric forms
(``0`` / ``1`` / ``2`` / ``3``); ``disc opt --help`` lists the full
mapping. ``EXEC`` is the right choice here because ``!BOOT`` is a
command file, not a binary — pressing :kbd:`SHIFT-BREAK` runs
``*EXEC $.!BOOT``, which effectively types the ``*RUN $.FS3v126``
line at the OS prompt.

**4. Attach the AFS partition.**

.. cli-example:: l3fs_disc
   :section: attach_afs

``disc afs-plan`` is a dry-run that shows the disc's geometry, how
many sectors ADFS currently occupies, and what an AFS partition
built from the remaining free space would look like. Reviewing the
plan before committing is the polite habit; ``afs-init`` then
carves out the AFS partition for real, adds an ``RJS`` regular
user, ``--omit-user``-s the built-in ``Welcome`` account, and
``--emplace``-s two shipped library images. ``Syst`` and ``Boot``
are not created explicitly — those are built-in accounts and arrive
for free with every freshly-initialised AFS partition (``Welcome``
would too, hence the explicit omission). The follow-up
``disc afs-users`` confirms the resulting user list: ``Syst``,
``Boot``, and ``RJS`` are present; ``Welcome`` is not. To change a
built-in's quota or password instead of dropping it, supply
``--user NAME:...`` and the spec overrides the default. Note also
the absence of ``--cylinders``: when omitted, ``afs-init`` claims
the existing free space, which is exactly what ``afs-plan`` would
have suggested. Pass an explicit value if you want a smaller AFS
region and ADFS retained beyond what is strictly necessary.
``--emplace`` accepts a shipped name (``Library``, ``Library1``,
``ArthurLib``) or a path to any ADFS ``.adl``; the contents land
in a directory of the same name on the AFS partition.

**5. Verify the dual-partition shape.**

.. cli-example:: l3fs_disc
   :section: verify

A final ``disc stat`` confirms the three-block layout — a ``Disc``
envelope carrying the physical geometry, then ``Partition 1: ADFS``
holding the boot configuration and the FS binary, then
``Partition 2: AFS`` ready to serve files over Econet. The
single-partition collapsed form documented in
:doc:`conventions/output-formats` does not apply here because the
two partitions genuinely carry different things; the envelope is
the natural umbrella.

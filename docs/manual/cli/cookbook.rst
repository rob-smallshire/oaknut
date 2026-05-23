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
``tests/data/images/cookbook/FS3v126.ssd``:

.. cli-example:: l3fs_disc

Reading top to bottom:

- **Build the ADFS half** (``disc create`` / ``cp`` / ``put``).
  ``disc create`` lays down a 10 MiB ADFS hard-disc envelope titled
  ``Server``. ``disc cp`` pulls the file-server binary out of the
  SSD it ships on and onto the new hard disc — a classic
  cross-image copy. ``disc put`` writes a one-line ``!BOOT`` whose
  contents are ``*RUN $.FS3v126`` followed by the Acorn ``\r`` line
  ending (built with ``printf`` into a local file we then feed to
  ``put`` — see :doc:`getting-started` for why ``printf`` rather
  than ``echo``).

- **Configure auto-boot** (``disc opt``). ``disc opt scsi0.dat``
  with no value reads the current boot option — ``0`` / ``OFF`` on
  a freshly-created disc. ``disc opt scsi0.dat EXEC`` sets it.
  Symbolic names (``OFF`` / ``LOAD`` / ``RUN`` / ``EXEC``) are
  accepted alongside the numeric forms (``0`` / ``1`` / ``2`` /
  ``3``); ``disc opt --help`` lists the full mapping. ``EXEC`` is
  the right choice here because ``!BOOT`` is a command file, not a
  binary — pressing :kbd:`SHIFT-BREAK` will run ``*EXEC $.!BOOT``,
  which types the ``*RUN $.FS3v126`` line at the OS prompt.

- **Attach the AFS partition** (``disc afs-plan`` / ``afs-init`` /
  ``afs-users``). ``disc afs-plan`` is a dry-run that shows the
  disc's geometry, how many sectors ADFS currently occupies, and
  what an AFS partition built from the remaining free space would
  look like. Reviewing the plan before committing is the polite
  habit; ``afs-init`` then carves out the AFS partition for real,
  adds an ``RJS`` regular user, ``--omit-user``-s the built-in
  ``Welcome`` account, and ``--emplace``-s two shipped library
  images. The recipe does **not** create ``Syst`` or ``Boot``
  explicitly — those are built-in accounts and arrive for free with
  every freshly-initialised AFS partition (``Welcome`` would too,
  hence the explicit omission). The follow-up ``disc afs-users``
  confirms the user list: ``Syst``, ``Boot``, and ``RJS`` are
  present; ``Welcome`` is not. To change a built-in's quota or
  password instead of dropping it, supply ``--user NAME:...`` and
  the spec overrides the default. Note also the absence of
  ``--cylinders``: when omitted, ``afs-init`` claims the existing
  free space, which is exactly what ``afs-plan`` would have
  suggested. Pass an explicit value if you want a smaller AFS
  region and ADFS retained beyond what is strictly necessary.
  ``--emplace`` accepts a shipped name (``Library``, ``Library1``,
  ``ArthurLib``) or a path to any ADFS ``.adl``; the contents land
  in a directory of the same name on the AFS partition.

- **Verify** (``disc stat``). The closing ``disc stat`` confirms the
  dual-partition shape — the same three-block layout
  (Disc envelope + Partition 1: ADFS + Partition 2: AFS) that
  :doc:`conventions/output-formats` describes, with the
  geometry block carrying information that is genuinely distinct
  from either partition's own slice.

Glossary
========

Project-specific vocabulary, in one place so other pages can use the
terms without parenthetical re-definition. Cross-referenced from
prose with the ``:term:`` role.

.. glossary::
   :sorted:

   ADFS
      *Advanced Disc Filing System.* Acorn's hierarchical filing
      system, used on the BBC Master, Archimedes, and RISC OS
      machines. Supports nested directories (paths read as
      ``$.Games.Elite``), per-file load/exec addresses, per-file
      access bits, and both floppy (``.adf``, ``.adl``) and
      hard-disc (``.dat``) images. Implemented by the ``oaknut-adfs``
      package.

   AFS
      The partition format used by the :term:`Acorn Level 3 File
      Server <Level 3 File Server>`. The four-byte magic at the head
      of the partition reads :term:`AFS0`, and the format is
      sometimes called *AFS0* by extension — pronounced "A F S zero"
      — when it needs to be distinguished from the broader notion of
      "an Acorn file server". No primary source records what the
      initialism originally stood for; treat it as a proper noun.

      An AFS partition always lives in the tail cylinders of an
      :term:`ADFS` hard-disc image. On a real Level 3 server, Econet
      clients reach files through the file server rather than ADFS
      directly. Implemented by the ``oaknut-afs`` package.

   AFS0
      The four-byte ASCII magic ``b"AFS0"`` at the start of the
      :term:`info sector` that opens an :term:`AFS` partition. Used
      loosely as an alternate name for the partition format itself.

   BBC BASIC
      Acorn's tokenised BASIC dialect, used on the BBC Micro,
      Electron, Archimedes, and RISC OS. Programs are stored on disc
      in a compact binary form — single-byte tokens for keywords,
      line numbers as two-byte big-endian — rather than as plain
      text. The ``oaknut.basic`` package round-trips between this
      on-disc form and a textual listing.

   BootOption
      The ``*OPT 4,n`` boot setting recorded in a :term:`DFS`
      catalogue or :term:`ADFS` root. One of ``OFF`` (``0``),
      ``LOAD`` (``1``), ``RUN`` (``2``), ``EXEC`` (``3``),
      controlling what the MOS does with ``$.!BOOT`` when the disc
      is booted with :kbd:`SHIFT-BREAK`. ``LOAD`` reads the file
      into memory, ``RUN`` executes it as a program, and ``EXEC``
      replays it as a script of typed lines.

   catalogue
      The on-disc index of files. On :term:`DFS`, two adjacent
      sectors at the start of the disc hold up to 31 entries (62 on
      :term:`Watford DDFS`). On :term:`ADFS` and :term:`AFS`, each
      directory is its own small catalogue. Always spelt British
      "catalogue" in this project, to match the Acorn-era
      convention.

   cylinder
      A vertical group of tracks at the same radial position across
      all surfaces of a disc. ADFS hard-disc geometry is reported in
      cylinders, and ``disc afs plan`` / ``disc afs init`` size the
      :term:`AFS` partition by cylinder boundary because the Level 3
      File Server's allocation tables address whole cylinders.

   DFS
      *Disc Filing System.* Acorn's original BBC Micro / Electron
      filing system, with a flat catalogue of up to 31 files keyed
      by a single-character directory letter and a seven-character
      filename. Floppy-only (``.ssd``, ``.dsd``). Implemented by the
      ``oaknut-dfs`` package, which also handles the
      :term:`Watford DDFS` and Opus DDOS extensions.

   Econet
      Acorn's lightweight two-wire LAN protocol, designed for
      schools and small offices. The transport :term:`Level 3 File
      Server` discs serve over; standalone DFS and ADFS images do
      not need Econet at all. oaknut does not implement the wire
      protocol — only the on-disc formats that file-server hosts
      consume.

   free space map
      The data structure that tracks which sectors on a disc are
      unused. On :term:`ADFS`, the FreeMap sits at the start of the
      image and lists free extents as ``(start, length)`` pairs. On
      :term:`AFS`, the equivalent role is played by a bitmap
      embedded in the partition's :term:`info sector`.

   info sector
      The 256-byte block at the head of an :term:`AFS` partition,
      carrying the :term:`AFS0` magic, the disc title, the
      :term:`SIN` of the root directory, the allocation bitmap, and
      assorted server-side bookkeeping. Stored in two copies
      (``sec1``, ``sec2``) for redundancy. Implemented by
      :class:`oaknut.afs.info_sector.InfoSector`.

   JesMap
      The 256-byte *map sector* that every file and directory in an
      :term:`AFS` partition carries, identified by the literal magic
      ``b"JesMap"`` at offset 0. Lists the runs of data sectors
      (extents) the object occupies — a file need not be contiguous
      on disc. The name appears verbatim in the original Level 3
      File Server sources; "Jes" is not documented as an initialism
      anywhere this project has been able to find. See
      :class:`oaknut.afs.map_sector.MapSector`.

   Level 3 File Server
      The Acorn server software that turns a host BBC machine into
      an Econet file server. Stores its files in an :term:`AFS`
      partition carved out of an :term:`ADFS` hard disc. "Level 3"
      distinguishes it from the earlier Level 1 and Level 2 servers,
      which stored files in DFS / ADFS without a separate format.

   MOS
      *Machine Operating System.* The BBC Micro's ROM-resident
      operating environment, providing the OSCLI dispatch, the file
      I/O vectors, and the star-command surface (``*CAT``,
      ``*LOAD``, ``*RUN``, …) that the ``disc '*…'`` aliases mirror.

   ROM
      *Read-Only Memory* chip. Acorn machines paged language and
      filing-system code in and out of a small set of ROM sockets.
      Most Acorn filing-system implementations — DFS, ADFS, Level 3
      FS — ship as a single sideways-ROM image that the MOS calls
      into.

   sector
      The smallest addressable unit on disc — 256 bytes throughout
      DFS, ADFS, and AFS. Every layout calculation in this codebase
      is expressed in sectors; load addresses are not.

   SIN
      *System Internal Name.* An :term:`AFS` file or directory's
      unique identifier inside the partition, equal to the disc
      address of its :term:`JesMap` map sector. Directory entries
      store SINs to refer to children, the way Unix dentries store
      inode numbers.

   Watford DDFS
      Watford Electronics's enhanced replacement for the stock
      Acorn :term:`DFS` ROM. Doubles the catalogue capacity from
      31 to 62 entries by spreading it across four sectors instead
      of two. ``oaknut.dfs`` reads and writes Watford-format discs
      without a separate mode switch — the catalogue layout is
      auto-detected.

   WFSINIT
      The Level 3 File Server's disc-initialisation utility, which
      partitions an :term:`ADFS` hard disc and writes the
      :term:`AFS` :term:`info sector`. ``oaknut.afs.wfsinit``
      reproduces this work in pure Python; ``disc afs init`` is the
      user-facing entry point.

   xattr
      *Extended file attribute.* A host-OS facility for attaching
      named key/value metadata directly to a file (without a
      sidecar). On Linux and macOS, oaknut can stash Acorn metadata
      (load address, exec address, access bits, file type) on the
      host data file itself rather than in a separate ``.inf``
      file. See :doc:`api/patterns/metadata` for the namespace and
      mapping rules.

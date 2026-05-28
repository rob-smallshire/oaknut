Metadata across the host boundary
=================================

Acorn files carry side-channel metadata that does not exist on a
modern host filesystem:

- a 32-bit **load address** (where the file goes in memory),
- a 32-bit **exec address** (where execution starts after load),
- an **access byte** (the L/W/R/E/PR/PW flags), and
- on RISC OS files, a 12-bit **filetype** encoded inside the load
  address.

A plain ``cp image.ssd:$.HELLO hello`` would lose every byte of
this — host filesystems do not have a column for "Acorn exec
address". The four commands that cross the host boundary —
``disc get``, ``disc put``, ``disc export``, ``disc import`` —
therefore accept a ``--meta-format`` option that names how
metadata is carried over the boundary. The choice has trade-offs,
and the wrong choice silently loses information. This page is the
single source of truth on what each format does and when each is
the right pick.


The four commands that cross the host boundary
----------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 22 25 53

   * - Command
     - Direction
     - Default ``--meta-format``
   * - ``disc get COMPOUND_PATH [HOST_PATH]``
     - image → host (one file)
     - ``inf-trad``
   * - ``disc put COMPOUND_PATH [HOST_PATH]``
     - host → image (one file)
     - import cascade (see :ref:`metadata-import-cascade`)
   * - ``disc export IMAGE HOST_DIR``
     - image → host (whole tree)
     - ``inf-trad``
   * - ``disc import IMAGE HOST_DIR``
     - host → image (whole tree)
     - import cascade

``disc cp`` between two image specs does **not** appear here — it
copies inside oaknut's own representation, so metadata travels
fully without needing a host side-channel. ``disc cat`` and
``disc type`` print only the file's bytes and never touch
metadata.


The ``--meta-format`` choices
-----------------------------

Every host-boundary command accepts the same seven values:

.. list-table::
   :header-rows: 1
   :widths: 20 25 55

   * - Value
     - What it carries
     - On-disk shape
   * - ``inf-trad``
     - filename, load, exec, length, attr
     - ``foo.bin`` plus ``foo.bin.inf`` containing
       ``$.FOO FFFF1900 FFFF8023 0040 [13]``
   * - ``inf-pieb``
     - load, exec, attr, owner
     - ``foo.bin`` plus ``foo.bin.inf`` in the PiEconetBridge form
       (no filename field; numeric owner instead)
   * - ``xattr-acorn``
     - load, exec, attr
     - ``foo.bin`` plus extended attributes
       ``user.acorn.load``, ``user.acorn.exec``,
       ``user.acorn.attr`` (uppercase hex)
   * - ``xattr-pieb``
     - load, exec, attr, owner
     - ``foo.bin`` plus extended attributes
       ``user.econet_load``, ``user.econet_exec``,
       ``user.econet_perm``, ``user.econet_owner``
   * - ``filename-riscos``
     - load, exec or filetype
     - Filename rewritten: ``foo,xxx`` for a filetype-stamped
       file, ``foo,llllllll,eeeeeeee`` (8+8 lowercase hex) otherwise
   * - ``filename-mos``
     - load, exec
     - Filename rewritten: ``foo,load-exec`` with variable-width
       lowercase hex separated by a hyphen
   * - ``none``
     - nothing
     - Just the bytes. Metadata is lost.

Pick based on what you want next:

**You want a single, widely-understood, archival-safe sidecar.**
Use ``inf-trad`` (the default). The ``.inf`` companion file is a
short text line every Acorn-era utility recognises, and it travels
through ZIP, tar, rsync, dropbox, USB sticks, and email
attachments unchanged.

**You are talking to a PiEconetBridge file server.**
Use ``inf-pieb`` (when staging files on disc) or ``xattr-pieb``
(when storing on a Linux filesystem PiEconetBridge will serve
from). These omit the Acorn filename field but include the Econet
owner ID — pass ``--owner N`` to set it.

**You want zero sidecar clutter and zero filename changes.**
Use ``xattr-acorn``. The metadata lives in extended attributes
attached directly to the file on disc. Caveat: xattrs survive
local copies on Linux/macOS but do not cross tar, ZIP, FAT,
SMB/CIFS shares, or most network protocols.

**You want metadata to survive any host conversion.**
Use ``filename-riscos`` or ``filename-mos``. The metadata is in
the filename, so anything that preserves the filename preserves
the metadata. ``filename-riscos`` is the modern RISC OS convention
(many emulators and converters speak it); ``filename-mos`` is the
older BBC MOS form.

**You explicitly do not want metadata** (the file is plain data and
will not go back).
Use ``none``. The file is written or read as raw bytes only.


.. _metadata-import-cascade:

What gets tried on import
-------------------------

``disc put`` and ``disc import`` without ``--meta-format`` try
each metadata source in turn, stopping at the first that yields
results:

1. **Traditional INF sidecar** — ``foo.bin.inf`` next to the data
   file. The line is parsed for load, exec, attr, and (for the
   traditional form) filename.
2. **Acorn xattrs** — ``user.acorn.*`` first; if absent, the
   reader also tries the PiEconetBridge ``user.econet_*``
   namespace before giving up on xattrs. A separate explicit
   ``--meta-format xattr-pieb`` cascade step would therefore be
   unreachable.
3. **RISC OS filename suffix** — ``,xxx`` or
   ``,llllllll,eeeeeeee`` at the end of the host filename.

If none of the three yield metadata, the file is imported with
``load_address=0``, ``exec_address=0``, and unlocked owner-R+W
access — the same defaults a fresh file would get from
``disc put`` followed by ``disc chmod``.

To override the cascade, pass ``--meta-format VALUE`` and only
that format is consulted. Pass ``--meta-format none`` to ignore
all metadata sources and import bytes only.


Overriding metadata at import time
----------------------------------

``disc put`` also accepts ``--load HEX`` and ``--exec HEX`` for
ad-hoc cases that don't fit any of the sidecar formats — for
example, putting a freshly-built binary onto a disc with an
explicit load address::

    disc put 'hello.ssd:$.PROG' build/prog.bin --load 0x1900 --exec 0x1900

These override whatever the chosen ``--meta-format`` would have
read.


Mixing formats in one direction
-------------------------------

The chosen format applies uniformly across a bulk command —
``disc export`` writes every file in the chosen ``--meta-format``.
For mixed exports (some files as INF, others as RISC OS filenames)
run ``disc get`` per file with different ``--meta-format``
values.

Imports are more flexible because the default cascade tries
multiple formats per file, so a host directory mixing INF
sidecars, xattr'd files, and filename-suffixed files imports
correctly as one ``disc import HOST_DIR`` invocation.


Cross-host gotchas
------------------

- **xattr survival depends on the filesystem and the transport.**
  Local Linux ext4 and macOS APFS preserve xattrs through ``cp``
  and ``mv``. ZIP, tar (without ``--xattrs``), FAT, exFAT, NTFS
  (the Linux driver), SMB/CIFS, and most cloud-storage clients
  strip them silently. If your files will travel, prefer
  ``inf-trad`` or ``filename-riscos``.
- **Sidecar files double the file count.** A directory of 1000
  Acorn files exported as ``inf-trad`` lands as 2000 host files.
  ``filename-riscos`` keeps the count at 1000 — useful for
  filename-sensitive contexts like ZIP archives.
- **Filename-encoded metadata changes the host filename.** A file
  saved as ``$.PROG`` exports under ``filename-riscos`` as
  ``PROG,FFFF1900,FFFF1900`` — handy for round-trip preservation,
  but you cannot also use the host filename to identify the file.
- **The Acorn-side filename is only preserved by ``inf-trad``.**
  All other formats use the host filename as the disc-side
  filename on re-import. If your Acorn filenames contain
  characters the host rejects (or vice-versa), the only
  round-trip-safe format is ``inf-trad``.

When in doubt, ``--meta-format inf-trad`` is the safest default
for archival and the most widely supported across other
Acorn-aware tooling.

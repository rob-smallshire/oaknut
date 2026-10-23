Acorn metadata on host filesystems
==================================

An Acorn file carries metadata that a modern host filesystem has no
place for: a load address, an execution address, an access byte, and
— on RISC OS — a filetype and a datestamp packed into those
addresses. Econet file servers add an owner, and some filing systems
add creation dates, account numbers, a boot option or a directory
title. When Acorn files are stored on Linux, macOS or Windows, or
travel through ZIP archives, emulators and network shares, this
metadata rides in one of a handful of side channels:

- a **sidecar file** beside each data file (the ``.inf`` family),
- a **suffix on the host filename** (``,ffb``, ``,8000-8023``),
- the **contents** of the file itself (Acorn NFS's ``,lxa`` files),
- **extended attributes** on the host file,
- an **extra field** in a ZIP archive's own structure, or
- a **per-directory attribute file** holding every entry's metadata.

This page describes each convention as its producers define it, with
the specification or source code each description is drawn from. It
is independent of any one tool; the closing section maps the
conventions onto oaknut's own options.


The metadata being carried
--------------------------

Load and execution addresses
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every Acorn filing system records two 32-bit words per file. On the
8-bit machines they are genuine addresses: where ``*LOAD`` puts the
file, and where ``*RUN`` enters it. An address of the form
``&FFFFxxxx`` belongs to the I/O processor (the BBC Micro itself)
rather than a Second Processor. DFS stores only 18 bits of each
address, so DFS-era tools often write six hex digits (``FF1900``);
the top byte ``FF`` stands for ``FFFF`` in the 32-bit form.

On RISC OS the same two words usually hold a **filetype and
datestamp** instead. When the top twelve bits of the load address are
``&FFF``, the load address reads ``&FFFtttdd`` and the exec address
``&dddddddd``: ``ttt`` is the 12-bit filetype, and the ten ``d``
digits form a 40-bit count of centiseconds since 00:00:00 on
1 January 1900. The marker overlaps genuine I/O-processor addresses,
so a pair of words alone does not say which reading applies; the
filing system and the era of the file do.

Access
~~~~~~

The access byte as the Stardot INF specification and the SparkFS ZIP
extra field define it:

.. list-table::
   :header-rows: 1
   :widths: 12 12 76

   * - Bit
     - Letter
     - Meaning
   * - ``&01``
     - ``R``
     - owner may read
   * - ``&02``
     - ``W``
     - owner may write
   * - ``&04``
     - ``E``
     - owner may execute (``*RUN``-only when ``R`` is clear)
   * - ``&08``
     - ``L``
     - locked: may not be deleted, overwritten or renamed
   * - ``&10``
     - ``r``
     - public may read
   * - ``&20``
     - ``w``
     - public may write
   * - ``&40``
     - ``e``
     - public may execute
   * - ``&80``
     - ``l``
     - public may not delete; the SparkFS field reserves this bit

Each filing system stores a subset. DFS records a single lock bit,
which also means read-only to DFS, and a DFS ``L`` is conventionally
widened to ``&19`` (``LR/R``) or narrowed to ``&08``. Econet file
servers and PiEconetBridge use other layouts, described with their
conventions below.

Other fields
~~~~~~~~~~~~

The less common fields are the file's length (redundant beside a host
file, but recorded by some sidecars), modification and creation dates
and times, user and auxiliary account numbers, an Econet owner, a
directory's ``*OPT 4`` boot option, a disc or directory title, and a
cassette or ROM filing system block CRC.


INF sidecar files
-----------------

An *INF file* is a one-line text file stored beside the data file it
describes, named after it with ``.inf`` appended. The format dates
from Wouter Scholten's ``bbcim`` and has grown several dialects.

Traditional INF: the Stardot specification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The `Stardot INF format specification`_, drafted by Tom Seddon in
September 2025 after a community review of the existing dialects in
the `Stardot *.inf format thread`_, describes what existing tools
write and sets rules for new ones. It is a draft and leaves some
questions open, which it lists. Its main rules:

**Naming.** The sidecar takes the data file's full host name plus
``.inf`` or ``.INF``, keeping any extension: ``ELITE.dat`` pairs with
``ELITE.dat.inf``. Readers on case-sensitive hosts try both cases.
The Acorn name inside the sidecar is authoritative, and a reader
confirms it matches before trusting a pairing.

**Line syntax.** Only the first line counts, ending at LF, CR, CR LF
or end of file; later lines are reserved. Fields are separated by
runs of spaces or tabs, and only 7-bit printable ASCII, space and tab
are allowed. The general shape is::

    [TAPE] name metadata… [KEY=value…] [NEXT name]

**Metadata fields.** The preferred form is a run of hex fields in
this order, of which any trailing ones may be omitted:

.. list-table::
   :header-rows: 1
   :widths: 10 90

   * - Field
     - Meaning
   * - 0
     - load address
   * - 1
     - execution address
   * - 2
     - length
   * - 3
     - access byte
   * - 4, 5
     - modification date, modification time
   * - 6, 7
     - creation date, creation time
   * - 8, 9
     - user account, auxiliary account

A writer emits 8-digit addresses and a 2-digit access byte::

    $.ELITE  FFFF1900 FFFF8023 00005000 13

Two short forms exist in the wild. TubeHost and BeebLink write up to
two addresses followed by a DFS-style access field, taking the length
from the data file; ADFS Explorer writes a directory's sidecar as a
lone access field.

**Access field.** Hex digits are the access byte. A symbolic field
uses the letters of the table above, case-sensitively — upper case
for the owner, lower case for the public — so ``WRr`` is ``&13``.
``D`` marks a directory and contributes no bit. A DFS-style field is
``L``, ``Locked`` or ``LOCKED``.

**Names.** A name containing spaces or other awkward characters is
written between double quotes, with ``"``, ``%`` and every byte
outside printable ASCII percent-encoded (``"MY FILE"``,
``"A%22B"``). Name bytes stay in the original machine's character
set; they are never converted to UTF-8.

**Extra fields.** ``KEY=value`` fields follow the metadata.
Recognised keys are ``CRC`` (CRC-16/XMODEM, the cassette checksum),
``CRC32`` (as used in ZIP), ``OPT`` (a directory's boot option),
``OPT4`` (the boot option, on a ``!BOOT`` file's sidecar), ``TITLE``
or ``DIRTITLE`` (a directory title) and ``DATETIME``
(``YYYYMMDDhhmmss``). Keys starting with ``_`` are reserved.

**Cassette markers.** A leading ``TAPE`` marks a file from cassette,
and a trailing ``NEXT`` names the following file on the tape. Readers
accept both; writers emit neither.

**Directories.** An Acorn directory is a host directory with its own
sidecar. DFS-style trees put each drive in one flat host directory;
ADFS-style trees mirror the hierarchy.

J.G. Harston's INF conventions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

J.G. Harston's `INF file format`_ and `Storing Acorn/BBC metadata on
other systems`_ pages document the same field order as written by
his ZipToInf, SJFiler, SoftMDFS and HostFS tools, with these
conventions:

- Writers pad the name to 11 columns, put one space between fields,
  use fixed widths (8 digits for addresses, 2 for access, 4 for dates
  and 6 for times), and end the line with CR LF. By default they
  write only the name, load, exec and length.
- Readers ignore extra spaces and unknown fields and accept missing
  leading zeros.
- An access field starting ``L`` reads as ``&19``, locked on DFS.
- An omitted exec address is the load address. An omitted access
  field is ``&33`` (``WR/WR``) when extracting from an archive.
- Extra fields are ``CRC=`` and ``BOOT=``, written in that order.
  ``BOOT=n`` carries what the Stardot specification calls ``OPT4``.

PiEconetBridge INF
~~~~~~~~~~~~~~~~~~

`PiEconetBridge`_, Chris Royle's Econet bridge and file server for the
Raspberry Pi, stores each file's attributes in extended attributes
(`see below <PiEconetBridge extended attributes_>`_), or in a sidecar
when extended attributes are turned off or a sidecar already exists.
Its sidecar is a different format that
shares the ``.inf`` name. Per ``utilities/fs.c`` in its source, the
sidecar for ``FRED`` is ``FRED.inf``, or ``FRED:inf`` when the
server's ``infcolon`` option is set, and holds a single line with no
line terminator::

    owner load exec perm [homeof]

All fields are hex with no leading zeros. There is no name field: the
host filename is the Acorn name, with Acorn ``/`` stored as ``:`` (or
``.`` under ``infcolon``) and a hard space (``&A0``) as ``#``.
``owner`` is the Econet user ID, and ``homeof`` the user whose home
directory this is. ``perm`` is not the Acorn access byte:

.. list-table::
   :header-rows: 1
   :widths: 12 88

   * - Bit
     - Meaning
   * - ``&01``
     - owner may read
   * - ``&02``
     - owner may write
   * - ``&04``
     - locked
   * - ``&08``
     - execute only
   * - ``&10``
     - others may read
   * - ``&20``
     - others may write
   * - ``&80``
     - hidden

The lock and execute bits are swapped relative to the Acorn byte, so
a reader converts between the two. The first field of a
PiEconetBridge line is a hex number and the first field of a
traditional line is a name, which is how a reader tells the formats
apart; a hex-looking name such as ``BEEF`` is ambiguous.

Per-directory attribute files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Two systems keep every entry's metadata in one file per directory.
SoftMDFS writes ``!!Metadata`` (or ``CHR$160+"Metadata"``), each line
holding a name, a tab and eight words of metadata as unbroken hex
(J.G. Harston, `Storing Acorn/BBC metadata on other systems`_). Acorn's
LanManFS, the RISC OS client for Windows shares, can write
``RISCOS.EA``, a binary file of fixed-size records of a 16-byte name
followed by the entry's RISC OS attributes (``c/Attr`` in the
`LanManFS source`_).


Filename suffixes
-----------------

RISC OS network filing systems and emulators encode the metadata in
the host filename itself, after the last comma in the name.

Filetype: ``,xxx``
~~~~~~~~~~~~~~~~~~

A three-digit hex filetype after a comma — ``Hello,ffb`` for a
tokenised BASIC program — is the most widely shared convention of
all. It began with Acorn NFS (`Omniclient User Guide: NFS file
mapping`_) and is written and read by LanManFS, the RPCEmu,
Arculator and ArcEm ``HostFS`` modules, and the Linux kernel's ADFS
driver under its ``ftsuffix`` option (`Linux ADFS filesystem`_). The
`application/riscos`_ MIME type registered by ANT Ltd in 1995 uses the
same form in its ``NAME`` parameter.

The suffix carries the filetype only. The datestamp travels as the
host file's modification time, and the access byte is lost or mapped
onto host permissions. A file with no suffix takes a default type,
which varies: Acorn NFS and the emulators omit the suffix for Text
(``&FFF``) and so read a bare name as Text, while LanManFS has a
configurable default and also consults a table of DOS extensions.

Acorn NFS: ``,lxa``
~~~~~~~~~~~~~~~~~~~

For a file with genuine load and execution addresses, Acorn NFS
appends the literal suffix ``,lxa`` to the name and appends the
addresses to the file's *contents*: eight extra bytes, the load
address then the exec address, each little-endian. On reading, it
hides the last eight bytes again. A ``,lxa`` file shorter than eight
bytes is malformed. NFS also uses the literal suffix ``,xxx`` for a
*dead* file, the RISC OS state of a file whose load did not complete
(`Omniclient User Guide: NFS file mapping`_).

Load and exec addresses: ``,load-exec``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

LanManFS and the RPCEmu, Arculator and ArcEm ``HostFS`` modules
write an untyped file's addresses in the name instead, as lowercase
hex of one to eight digits separated by a hyphen::

    Game,1900-8023
    Utility,ffff0e00-ffff0e00

Readers accept one to eight hex digits on each side (``Xlate.c`` in the
`LanManFS source`_; ``hostfs.c`` in `RPCEmu`_ and `Arculator`_).

Load and exec addresses: ``,llllllll,eeeeeeee``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Justin Fletcher's `python-zipinfo-riscos`_ library writes an untyped
file as two eight-digit lowercase hex words, each after a comma::

    Game,00001900,00008023

It writes typed files with the ``,xxx`` suffix. The ``HostFS`` modules
and LanManFS do not read this form: they take the text after the
*last* comma, find eight digits with no hyphen, and keep the whole
string as the filename.

Character translation
~~~~~~~~~~~~~~~~~~~~~

Each of these systems also translates the characters that differ in
meaning between Acorn and host filenames. The common core, as
implemented by RPCEmu's ``HostFS``, swaps the two separators and maps
characters that hosts reserve:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Acorn
     - Host
     - Note
   * - ``.``
     - ``/``
     - directory separator
   * - ``/``
     - ``.``
     - so ``fred/c`` is ``fred.c``
   * - ``?``
     - ``#``
     -
   * - ``<``
     - ``$``
     -
   * - ``>``
     - ``^``
     -
   * - hard space (``&A0``)
     - space
     -

J.G. Harston's ZIP conventions add ``=`` ↔ ``@``, ``&`` ↔ ``+`` and
``%`` ↔ ``;``, with spaces converted one way to ``_`` (`Storing
Acorn/BBC metadata on other systems`_). PiEconetBridge, as noted
above, stores ``/`` as ``:``.


Extended attributes
-------------------

Linux and macOS can attach named attributes to a file, keeping the
metadata with the data file without a sidecar or a renamed file.
Two attribute namespaces are established for Acorn files. All values
are uppercase hex text.

PiEconetBridge extended attributes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

PiEconetBridge's default store, per ``utilities/fs.c`` in
`PiEconetBridge`_:

.. list-table::
   :header-rows: 1
   :widths: 35 15 50

   * - Attribute
     - Digits
     - Value
   * - ``user.econet_owner``
     - 4
     - Econet user ID
   * - ``user.econet_load``
     - 8
     - load address
   * - ``user.econet_exec``
     - 8
     - execution address
   * - ``user.econet_perm``
     - 2
     - PiEconetBridge ``perm`` byte (layout as for its INF)
   * - ``user.econet_homeof``
     - 4
     - user whose home directory this is

The project ships shell scripts to convert between these attributes
and its INF sidecars.

``user.acorn.*`` attributes
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The oaknut libraries write ``user.acorn.load`` and
``user.acorn.exec`` (eight digits each) and ``user.acorn.attr`` (the
two-digit Acorn access byte). The `nautilus-acornfs`_ FUSE
filesystem, which presents mounted Acorn images in the GNOME file
manager, exposes ``user.acorn.load`` with the exec address under
``user.acorn.execute`` and the filetype, lock bit and Acorn path
under further ``user.acorn.*`` names.

On macOS the names have no namespace prefix of their own, so tools
use the same strings verbatim.

Extended attributes stay with a file through local copies and moves
on the same kind of filesystem. tar without ``--xattrs``, ZIP, FAT
and exFAT volumes, SMB shares and most cloud-storage clients drop
them without warning.


ZIP archives
------------

The SparkFS extra field
~~~~~~~~~~~~~~~~~~~~~~~

David Pilling's SparkFS defined a ZIP *extra field* that RISC OS
archivers write for every member, registered as header ID
``0x4341`` ("AC") in the `Info-ZIP extra field registry`_. Values are
little-endian, and the local and central headers carry identical
copies:

.. list-table::
   :header-rows: 1
   :widths: 12 10 78

   * - Offset
     - Size
     - Field
   * - 0
     - 2
     - header ID ``0x4341``
   * - 2
     - 2
     - data size (20, or 28 with the optional fields)
   * - 4
     - 4
     - signature ``ARC0``
   * - 8
     - 4
     - load address (or filetype and datestamp)
   * - 12
     - 4
     - execution address
   * - 16
     - 4
     - attributes: the access byte in the low eight bits
   * - 20
     - 4
     - reserved, zero
   * - 24
     - 2
     - creation time, MS-DOS format (optional)
   * - 26
     - 2
     - creation date, MS-DOS format (optional)
   * - 28
     - 2
     - main account (optional)
   * - 30
     - 2
     - auxiliary account (optional)

The optional fields are described in J.G. Harston's `ZIP extra field
notes`_. The modification date and time come from the ZIP header's
own DOS fields. When a member has no extra field, J.G. Harston's
defaults apply on extraction: load 0, exec equal to load, access
``&33``.

Other metadata in ZIP files
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Archives assembled on other platforms carry the metadata in the
forms already described: ``.inf`` sidecars stored as archive members
beside their data files, or filename suffixes on the member names.
A reader that meets several sources for one member treats the extra
field as the most authoritative, since it is part of the archive
structure rather than a convention layered on it.


Which convention survives what
------------------------------

.. list-table::
   :header-rows: 1
   :widths: 28 18 18 18 18

   * - Transport
     - INF sidecar
     - Filename suffix
     - Extended attributes
     - SparkFS extra field
   * - Local copy, same filesystem
     - yes
     - yes
     - yes
     - —
   * - ZIP or tar archive
     - yes
     - yes
     - no (tar: only with ``--xattrs``)
     - ZIP only
   * - FAT, exFAT, SMB share
     - yes
     - yes, if the suffix is a legal name
     - no
     - —
   * - Email, cloud storage, web download
     - only if both files travel
     - yes
     - no
     - inside the ZIP

Only the INF sidecar records the Acorn filename independently of the
host name, so it alone survives an Acorn name the host cannot
represent. Filename suffixes carry no access at all; INF sidecars,
the SparkFS extra field and the extended-attribute namespaces do.


In oaknut
---------

The ``disc`` and ``zip`` tools read and write these conventions
through the ``--meta-format`` option, described in
:doc:`cli/conventions/metadata`:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - ``--meta-format``
     - Convention
   * - ``inf-trad``
     - traditional INF, per the Stardot specification
   * - ``inf-pieb``
     - PiEconetBridge INF
   * - ``xattr-acorn``
     - ``user.acorn.load``, ``user.acorn.exec``, ``user.acorn.attr``
   * - ``xattr-pieb``
     - PiEconetBridge extended attributes
   * - ``filename-riscos``
     - ``,xxx`` for typed files, ``,llllllll,eeeeeeee`` for untyped
   * - ``filename-mos``
     - ``,load-exec``, the LanManFS and ``HostFS`` form

``oaknut.zip`` reads the SparkFS extra field.


References
----------

Specifications and format notes:

- `Stardot INF format specification`_ — Tom Seddon, draft, 2025.
- `Stardot *.inf format thread`_ — the 2025 community discussion that
  led to the specification, started by Gerald Holdsworth.
- `INF file format`_ — J.G. Harston, mdfs.net.
- `Storing Acorn/BBC metadata on other systems`_ — J.G. Harston,
  mdfs.net: INF, ZIP, SoftMDFS and archive formats, with character
  mappings and defaults.
- `ZIP extra field notes`_ — J.G. Harston, mdfs.net.
- `Info-ZIP extra field registry`_ — ``extrafld.txt``, including the
  Acorn/SparkFS block.
- `Omniclient User Guide: NFS file mapping`_ — Acorn NFS's ``,xxx``,
  ``,lxa`` and character mappings.
- `application/riscos`_ — IANA media type registration, ANT Ltd, 1995.
- `Linux ADFS filesystem`_ — the kernel's ``ftsuffix`` option.

Source code:

- `PiEconetBridge`_ — ``utilities/fs.c``: INF sidecars and
  ``user.econet_*`` attributes.
- `LanManFS source`_ — ``c/Attr`` and ``c/Xlate``: ``RISCOS.EA``, the
  ``,xxx`` and ``,load-exec`` suffixes.
- `RPCEmu`_ and `Arculator`_ — ``HostFS``: the ``,xxx`` and
  ``,load-exec`` suffixes and character translation.
- `python-zipinfo-riscos`_ — the ``,llllllll,eeeeeeee`` suffix and the
  SparkFS extra field in Python.
- `nautilus-acornfs`_ — ``user.acorn.*`` attributes on mounted images.

.. _Stardot INF format specification: https://github.com/stardot/inf_format/blob/main/inf_format_full.md
.. _Stardot *.inf format thread: https://stardot.org.uk/forums/viewtopic.php?t=31577
.. _INF file format: https://mdfs.net/Docs/Comp/BBC/FileFormat/INFfile
.. _Storing Acorn/BBC metadata on other systems: https://mdfs.net/Docs/Comp/BBC/Filing/Metadata
.. _ZIP extra field notes: https://mdfs.net/Docs/Comp/Archiving/Zip/ExtraField
.. _Info-ZIP extra field registry: https://libzip.org/specifications/extrafld.txt
.. _Omniclient User Guide\: NFS file mapping: http://www.riscos.com/support/users/omniclient/6_filemap.html
.. _application/riscos: https://www.iana.org/assignments/media-types/application/riscos
.. _Linux ADFS filesystem: https://docs.kernel.org/filesystems/adfs.html
.. _PiEconetBridge: https://github.com/cr12925/PiEconetBridge
.. _LanManFS source: https://github.com/TimothyEBaldwin/RISC_OS_Linux_Source/tree/HEAD/RiscOS/Sources/Networking/Omni/Protocols/OmniLanManFS
.. _RPCEmu: http://www.marutan.net/rpcemu/
.. _Arculator: https://github.com/sarah-walker-pcem/arculator
.. _python-zipinfo-riscos: https://github.com/gerph/python-zipinfo-riscos
.. _nautilus-acornfs: https://github.com/peteclarke-del/nautilus-acornfs

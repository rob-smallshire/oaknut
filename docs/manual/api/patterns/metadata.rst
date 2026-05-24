File metadata
=============

Acorn files carry side-channel metadata — a 32-bit load address, a
32-bit exec address, an access byte (the L/W/R/E/PR/PW flag set),
and (under RISC OS) a 12-bit filetype. None of this travels through
a plain host ``cp``, so :mod:`oaknut.file` provides:

- A canonical :class:`~oaknut.file.AcornMeta` dataclass to hold the
  metadata for one file.
- A small enum of :class:`~oaknut.file.MetaFormat` values naming
  the side-channels the metadata can live in on a host filesystem.
- A pair of helpers — :func:`~oaknut.file.export_with_metadata` and
  :func:`~oaknut.file.import_with_metadata` — that move bytes plus
  metadata across the host boundary using one of those formats.

The Acorn-side filing systems (DFS, ADFS, AFS) store the same fields
natively in their on-disc directory entries. The cross-host formats
exist to keep the fields alive when files leave the disc image.


AcornMeta
---------

.. autoclass:: oaknut.file.AcornMeta
   :members:

Two derived properties are worth flagging. RISC OS encodes a
filetype inside the top bits of the load address when bits 20–31
equal ``0xFFF``; :attr:`AcornMeta.is_filetype_stamped` says whether
this convention applies and :meth:`AcornMeta.infer_filetype`
extracts the 12-bit filetype value when it does.


Access
------

.. autoclass:: oaknut.file.Access
   :members:

The integer value of an :class:`Access` combination is the standard
Acorn attribute byte (``int(Access.LWR) == 0x0B``), so it can be
stored directly in xattrs, INF lines, or any other byte-sized
slot. The :func:`~oaknut.file.parse_access` and matching
:func:`~oaknut.file.format_access_text` / :func:`~oaknut.file.format_access_hex`
helpers convert to and from the textual forms (``"LWR/R"``, ``"0B"``,
etc.) that show up in INF sidecars and CLI output.


BootOption
----------

.. autoclass:: oaknut.file.BootOption
   :members:

The disc-level boot option (``*OPT 4,n``) sits next to file
metadata because it is read and written through the same per-disc
catalogues — ``OFF``, ``LOAD``, ``RUN``, and ``EXEC`` match the
four values the BBC's ``OPT`` command accepts. Both
:attr:`DFS.boot_option <oaknut.dfs.DFS.boot_option>` and
:attr:`ADFS.boot_option <oaknut.adfs.ADFS.boot_option>` return a
:class:`BootOption` and accept either a :class:`BootOption` or a
plain ``int`` on assignment.


MetaFormat — host-side metadata side-channels
---------------------------------------------

.. autoclass:: oaknut.file.MetaFormat
   :members:

The values are:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Value
     - Format
   * - ``INF_TRAD``
     - Traditional ``.inf`` sidecar — a single text line carrying
       ``filename load_address exec_address length [attr]``.
       Default for export; widely supported by Acorn-era tooling.
   * - ``INF_PIEB``
     - PiEconetBridge ``.inf`` flavour — ``load_address
       exec_address attr owner``, no filename field. Used when
       interoperating with PiEconetBridge file servers.
   * - ``XATTR_ACORN``
     - Filesystem extended attributes under the ``user.acorn.*``
       namespace: ``user.acorn.load``, ``user.acorn.exec``, and
       ``user.acorn.attr`` (uppercase hex strings).
   * - ``XATTR_PIEB``
     - Filesystem extended attributes under the ``user.econet_*``
       namespace (the PiEconetBridge convention): ``user.econet_load``,
       ``user.econet_exec``, ``user.econet_perm``, and
       ``user.econet_owner``.
   * - ``FILENAME_RISCOS``
     - Metadata in the filename itself, RISC OS style. Either
       ``name,xxx`` (a 3-digit hex filetype) or
       ``name,llllllll,eeeeeeee`` (8-hex load + 8-hex exec) when
       the file is not filetype-stamped.
   * - ``FILENAME_MOS``
     - Metadata in the filename, BBC MOS style:
       ``name,load-exec`` with variable-width lowercase hex
       separated by a hyphen.

Two host-side helpers compose the formats with file I/O:

.. autofunction:: oaknut.file.export_with_metadata

.. autofunction:: oaknut.file.import_with_metadata

Path objects on every filesystem wrap these helpers so the common
case is one method call: :meth:`export_file` writes bytes plus
metadata in the chosen format; :meth:`import_file` reads bytes plus
metadata by trying the import cascade. See the
:doc:`/api/cookbook` "Round-tripping a file through the host
filesystem" recipe for a worked example.


Default cascades
----------------

Exports default to :attr:`MetaFormat.INF_TRAD` — the most widely
recognised format. Override with the ``meta_format=`` keyword on
:meth:`export_file` or :func:`export_with_metadata`.

Imports try a cascade in the order
:data:`oaknut.file.DEFAULT_IMPORT_META_FORMATS`:

1. ``INF_TRAD`` — the traditional sidecar form.
2. ``XATTR_ACORN`` — the preferred xattr namespace. The reader
   automatically falls back to ``user.econet_*`` when the
   ``user.acorn.*`` keys are absent on a file, so a separate
   ``XATTR_PIEB`` step in the cascade would be unreachable.
3. ``FILENAME_RISCOS`` — the RISC OS filename suffix.

Callers can pass a different ``meta_formats=`` sequence to
override the cascade — for example, listing ``XATTR_PIEB`` ahead
of ``XATTR_ACORN`` when the source-of-truth on the host is known
to be the PiEconetBridge namespace.

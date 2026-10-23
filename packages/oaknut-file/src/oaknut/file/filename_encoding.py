"""Filename metadata encoding schemes.

Three conventions for encoding Acorn file metadata in host filenames:

- **Filetype**: ``filename,xxx`` (3-digit hex filetype), as Acorn NFS,
  LanManFS and the RISC OS emulators' HostFS modules write.
- **Load/exec, hyphenated**: ``filename,load-exec`` (variable-width
  hex), as LanManFS and the HostFS modules write for untyped files.
- **Load/exec, fixed width**: ``filename,llllllll,eeeeeeee`` (8+8 digit
  hex), as python-zipinfo-riscos writes. Read only.

See ``docs/disc/host-metadata.rst`` for the sources of each.
"""

from __future__ import annotations

import re
import warnings

from oaknut.file.meta import AcornMeta

# Regex patterns for each encoding scheme
SUFFIX_FILETYPE_RE = re.compile(r"^(.*),([0-9a-fA-F]{3})$")
SUFFIX_FIXED_LOADEXEC_RE = re.compile(r"^(.*),([0-9a-fA-F]{8}),([0-9a-fA-F]{8})$")
SUFFIX_LOADEXEC_RE = re.compile(r"^(.*),([0-9a-fA-F]{1,8})-([0-9a-fA-F]{1,8})$")


def parse_encoded_filename(filename: str) -> tuple[str, AcornMeta | None]:
    """Strip metadata suffix from a filename.

    Tries each encoding scheme in order: fixed-width load/exec,
    hyphenated load/exec, filetype. Returns ``(clean_filename, metadata)``
    where *metadata* is ``None`` if no encoding was found.
    """
    # Try fixed-width load/exec first (most specific: 8+8 digits)
    m = SUFFIX_FIXED_LOADEXEC_RE.match(filename)
    if m:
        load_address = int(m.group(2), 16)
        exec_address = int(m.group(3), 16)
        return m.group(1), AcornMeta(load_address=load_address, exec_address=exec_address)

    # Try hyphenated load/exec (variable width)
    m = SUFFIX_LOADEXEC_RE.match(filename)
    if m:
        load_address = int(m.group(2), 16)
        exec_address = int(m.group(3), 16)
        return m.group(1), AcornMeta(load_address=load_address, exec_address=exec_address)

    # Try filetype (3-digit hex)
    m = SUFFIX_FILETYPE_RE.match(filename)
    if m:
        filetype = int(m.group(2), 16)
        # Synthesise a RISC OS load address from the filetype
        load_address = 0xFFF00000 | (filetype << 8)
        return m.group(1), AcornMeta(
            load_address=load_address,
            exec_address=0,
            filetype=filetype,
        )

    return filename, None


def build_filename_suffix(meta: AcornMeta) -> str:
    """Build a RISC OS filename encoding suffix.

    Returns ``,xxx`` for filetype-stamped files, or ``,load-exec`` for
    literal load/exec addresses — the forms RISC OS LanManFS and the
    HostFS modules read.
    """
    if meta.is_filetype_stamped:
        ft = meta.infer_filetype()
        return f",{ft:03x}"
    return build_loadexec_filename_suffix(meta)


def build_loadexec_filename_suffix(meta: AcornMeta) -> str:
    """Build a load/exec filename encoding suffix.

    Returns ``,load-exec`` with variable-width lowercase hex, whether or
    not the file is filetype-stamped, so a filetype's datestamp survives
    in the name.
    """
    return f",{meta.load_address:x}-{meta.exec_address:x}"


def build_mos_filename_suffix(meta: AcornMeta) -> str:
    """Deprecated alias for :func:`build_loadexec_filename_suffix`."""
    warnings.warn(
        "build_mos_filename_suffix() is deprecated; use build_loadexec_filename_suffix().",
        DeprecationWarning,
        stacklevel=2,
    )
    return build_loadexec_filename_suffix(meta)

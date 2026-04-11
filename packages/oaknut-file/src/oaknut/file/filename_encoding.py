"""Filename metadata encoding schemes.

Three conventions for encoding Acorn file metadata in host filenames:

- **RISC OS filetype**: ``filename,xxx`` (3-digit hex filetype)
- **RISC OS load/exec**: ``filename,llllllll,eeeeeeee`` (8+8 digit hex)
- **MOS load/exec**: ``filename,load-exec`` (variable-width hex)
"""

from __future__ import annotations

import re

from oaknut.file.meta import AcornMeta

# Regex patterns for each encoding scheme
SUFFIX_FILETYPE_RE = re.compile(r"^(.*),([0-9a-fA-F]{3})$")
SUFFIX_LOADEXEC_RE = re.compile(r"^(.*),([0-9a-fA-F]{8}),([0-9a-fA-F]{8})$")
SUFFIX_MOS_LOADEXEC_RE = re.compile(r"^(.*),([0-9a-fA-F]{1,8})-([0-9a-fA-F]{1,8})$")


def parse_encoded_filename(filename: str) -> tuple[str, AcornMeta | None]:
    """Strip metadata suffix from a filename.

    Tries each encoding scheme in order: RISC OS load/exec,
    MOS load/exec, filetype. Returns ``(clean_filename, metadata)``
    where *metadata* is ``None`` if no encoding was found.
    """
    # Try RISC OS load/exec first (most specific: 8+8 digits)
    m = SUFFIX_LOADEXEC_RE.match(filename)
    if m:
        load_addr = int(m.group(2), 16)
        exec_addr = int(m.group(3), 16)
        return m.group(1), AcornMeta(load_addr=load_addr, exec_addr=exec_addr)

    # Try MOS load/exec (variable-width with hyphen)
    m = SUFFIX_MOS_LOADEXEC_RE.match(filename)
    if m:
        load_addr = int(m.group(2), 16)
        exec_addr = int(m.group(3), 16)
        return m.group(1), AcornMeta(load_addr=load_addr, exec_addr=exec_addr)

    # Try filetype (3-digit hex)
    m = SUFFIX_FILETYPE_RE.match(filename)
    if m:
        filetype = int(m.group(2), 16)
        # Synthesise a RISC OS load address from the filetype
        load_addr = 0xFFF00000 | (filetype << 8)
        return m.group(1), AcornMeta(
            load_addr=load_addr,
            exec_addr=0,
            filetype=filetype,
        )

    return filename, None


def build_filename_suffix(meta: AcornMeta) -> str:
    """Build a RISC OS filename encoding suffix.

    Returns ``,xxx`` for filetype-stamped files, or
    ``,llllllll,eeeeeeee`` for literal load/exec addresses.
    """
    if meta.is_filetype_stamped:
        ft = meta.infer_filetype()
        return f",{ft:03x}"
    return f",{meta.load_addr:08x},{meta.exec_addr:08x}"


def build_mos_filename_suffix(meta: AcornMeta) -> str:
    """Build a MOS filename encoding suffix.

    Returns ``,load-exec`` with variable-width lowercase hex.
    """
    return f",{meta.load_addr:x}-{meta.exec_addr:x}"

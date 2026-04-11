"""Acorn file access attributes.

The ``Access`` IntFlag enum represents the standard Acorn OSFILE
attribute byte. Bit values match the filing system API convention,
ensuring compatibility with PiEconetBridge ``perm`` and the
``user.acorn.attr`` extended attribute.
"""

from __future__ import annotations

from enum import IntFlag


class Access(IntFlag):
    """Acorn file access attributes.

    Composable with ``|``::

        Access.R | Access.W | Access.L
        Access.R | Access.W | Access.PR  # with public read

    The integer value of a combination is the standard Acorn
    attribute byte, suitable for storage in xattrs or INF files::

        int(Access.R | Access.W)  # 0x03
    """

    R  = 0x01  # Owner read
    W  = 0x02  # Owner write
    E  = 0x04  # Execute only
    L  = 0x08  # Locked (prevents delete, overwrite, rename)
    PR = 0x10  # Public read
    PW = 0x20  # Public write


def format_access_hex(attr: int | None) -> str:
    """Format an attribute byte as a two-digit uppercase hex string.

    Returns empty string for None.
    """
    if attr is None:
        return ""
    return f"{attr:02X}"


def format_access_text(attr: int | None) -> str:
    """Format attributes as a human-readable access string.

    Returns ``"owner/public"`` form, e.g. ``"LWR/R"``.
    """
    if attr is None:
        return "/"

    owner = ""
    if attr & Access.L:
        owner += "L"
    if attr & Access.W:
        owner += "W"
    if attr & Access.R:
        owner += "R"

    public = ""
    if attr & Access.PW:
        public += "W"
    if attr & Access.PR:
        public += "R"

    return f"{owner}/{public}"

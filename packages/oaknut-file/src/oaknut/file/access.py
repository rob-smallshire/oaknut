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

    R = 0x01  # Owner read
    W = 0x02  # Owner write
    E = 0x04  # Execute only
    L = 0x08  # Locked (prevents delete, overwrite, rename)
    PR = 0x10  # Public read
    PW = 0x20  # Public write


_OWNER_LETTERS = {"L": Access.L, "W": Access.W, "R": Access.R, "E": Access.E}
_PUBLIC_LETTERS = {"W": Access.PW, "R": Access.PR}


def parse_access(text: str) -> Access:
    """Parse an access string back to an ``Access`` value.

    Accepts three forms:

    - **Symbolic**: ``"LWR/R"``, ``"WR/WR"``, ``"R/"`` — letters
      before the slash are owner flags (L, W, R, E), letters after
      are public flags (W, R). Case-insensitive. A missing slash
      treats the entire string as owner flags.
    - **Hex with prefix**: ``"0x0B"``, ``"0x33"`` — parsed as an
      integer.
    - **Bare hex**: ``"0B"``, ``"33"`` — two hex digits without
      prefix.

    Raises :class:`ValueError` on unrecognised input.
    """
    stripped = text.strip()

    # Hex with 0x prefix.
    if stripped.lower().startswith("0x"):
        return Access(int(stripped, 16))

    # Bare hex: exactly two hex digits, no letters outside [0-9A-Fa-f].
    if len(stripped) == 2 and all(c in "0123456789ABCDEFabcdef" for c in stripped):
        # Disambiguate from symbolic: "WR" has letters that are valid
        # access flags *and* valid hex digits. If both chars are valid
        # flag letters (L, W, R, E) *and* valid hex, prefer symbolic.
        upper = stripped.upper()
        all_flag_letters = all(c in "LWRE" for c in upper)
        if not all_flag_letters:
            return Access(int(stripped, 16))

    # Symbolic: owner/public or owner-only.
    if "/" in stripped:
        owner_part, public_part = stripped.split("/", 1)
    else:
        owner_part = stripped
        public_part = ""

    result = Access(0)
    for ch in owner_part.upper():
        if ch not in _OWNER_LETTERS:
            raise ValueError(f"unrecognised owner access letter '{ch}'")
        result |= _OWNER_LETTERS[ch]
    for ch in public_part.upper():
        if ch not in _PUBLIC_LETTERS:
            raise ValueError(f"unrecognised public access letter '{ch}'")
        result |= _PUBLIC_LETTERS[ch]
    return result


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

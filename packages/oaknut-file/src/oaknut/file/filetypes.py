"""RISC OS filetype names.

A RISC OS filetype is a 12-bit number. A few hundred are registered;
this table carries the well-known system range (``0xF00``–``0xFFF``)
and a handful of common others, enough to label what turns up on Acorn
media. An unrecognised number renders as ``&XXX`` and still round-trips.
The central registry is maintained by RISC OS Open.
"""

from __future__ import annotations

from oaknut.file.exceptions import InvalidFiletypeError

#: filetype number -> canonical name. Names are matched case-insensitively
#: on the way back in (:func:`parse_filetype`).
FILETYPE_NAMES: dict[int, str] = {
    0xFFF: "Text",
    0xFFE: "Command",
    0xFFD: "Data",
    0xFFC: "Utility",
    0xFFB: "BASIC",
    0xFFA: "Module",
    0xFF9: "Sprite",
    0xFF8: "Absolute",
    0xFF7: "BBCFont",
    0xFF6: "Font",
    0xFF5: "PoScript",
    0xFF4: "Printout",
    0xFF3: "LaserJet",
    0xFF0: "TIFF",
    0xFED: "Palette",
    0xFEC: "Template",
    0xFEB: "Obey",
    0xFEA: "Desktop",
    0xFE4: "DOS",
    0xFCA: "Squash",
    0xFAF: "HTML",
    0xDDC: "Archive",
    0xC85: "JPEG",
    0xB60: "PNG",
    0xAFF: "DrawFile",
}

#: name (lower-cased) -> filetype number, for parsing.
_NAMES_TO_NUMBERS: dict[str, int] = {
    name.lower(): number for number, name in FILETYPE_NAMES.items()
}


def filetype_name(filetype: int) -> str:
    """The canonical name for a filetype, or its ``&XXX`` hex form."""
    name = FILETYPE_NAMES.get(filetype)
    if name is not None:
        return name
    return f"&{filetype:03X}"


def parse_filetype(text: str) -> int:
    """Parse a filetype from a name or a numeric literal.

    Accepts a registered name (case-insensitive), an Acorn ``&xxx``
    hex literal, a Python ``0x``/``0o``/``0b``/decimal literal, or the
    ``&XXX`` form :func:`filetype_name` emits for an unknown type.
    Unrecognised text or an out-of-range number raises
    :class:`~oaknut.file.exceptions.InvalidFiletypeError`.
    """
    candidate = text.strip()
    number = _NAMES_TO_NUMBERS.get(candidate.lower())
    if number is None:
        literal = candidate
        if literal[:1] == "&":
            literal = "0x" + literal[1:]
        try:
            number = int(literal, 0)
        except ValueError:
            raise InvalidFiletypeError(
                f"{text!r} is not a known filetype name or number"
            ) from None
    if not 0 <= number <= 0xFFF:
        raise InvalidFiletypeError(
            f"filetype {text!r} is out of range (000–FFF)"
        )
    return number

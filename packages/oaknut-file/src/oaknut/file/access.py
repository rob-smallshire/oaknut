"""Acorn file access attributes.

The ``Access`` IntFlag enum represents the standard Acorn OSFILE
attribute byte. Bit values match the filing system API convention,
ensuring compatibility with PiEconetBridge ``perm`` and the
``user.acorn.attr`` extended attribute.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import IntFlag

from oaknut.file.exceptions import InvalidAccessError


class Access(IntFlag):
    """Acorn file access attributes.

    Composable with ``|``::

        Access.R | Access.W | Access.L
        Access.R | Access.W | Access.PR  # with public read

    The integer value of a combination is the standard Acorn
    attribute byte, suitable for storage in xattrs or INF files::

        int(Access.R | Access.W)  # 0x03

    Two convenience composites cover the cases that come up in every
    write_bytes call site:

      - :attr:`Access.WR` — owner read+write (the filesystem default
        for a newly-created file).
      - :attr:`Access.LWR` — locked owner read+write (a file that
        should not be deleted, overwritten, or renamed). Pass this
        as ``access=Access.LWR`` for the locked-default case.
    """

    R = 0x01  # Owner read
    W = 0x02  # Owner write
    E = 0x04  # Execute only
    L = 0x08  # Locked (prevents delete, overwrite, rename — disc filesystems)
    PR = 0x10  # Public read
    PW = 0x20  # Public write
    X = 0x40  # Run-only: may be *RUN but not *LOADed (CFS/ROMFS copy protection)

    # Convenience composites.
    WR = R | W
    LWR = L | R | W


#: ``X`` (run-only) is a distinct axis from ``L`` (delete-lock): it is the
#: cassette/ROM filing-system copy protection (a file that may be *RUN but
#: not *LOADed), and does not map to or from the disc filesystems' lock.
_OWNER_LETTERS = {"L": Access.L, "W": Access.W, "R": Access.R, "E": Access.E, "X": Access.X}
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

    Raises :class:`~oaknut.file.exceptions.InvalidAccessError` on
    unrecognised input (a subclass of :class:`ValueError`, so existing
    ``except ValueError`` handlers keep working, while the CLI boundary
    renders it cleanly without a traceback).
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
    return _parse_letters(stripped)


def _parse_letters(text: str) -> Access:
    """Parse an ``owner/public`` (or owner-only) letter group into an ``Access``.

    Shared by the symbolic branch of :func:`parse_access` and by each
    ``+``/``-`` clause of :func:`parse_access_spec`. Letters before the slash
    are owner flags (L, W, R, E, X); letters after are public flags (W, R).
    """
    if "/" in text:
        owner_part, public_part = text.split("/", 1)
    else:
        owner_part, public_part = text, ""

    result = Access(0)
    for ch in owner_part.upper():
        if ch not in _OWNER_LETTERS:
            raise InvalidAccessError(f"unrecognised owner access letter '{ch}'")
        result |= _OWNER_LETTERS[ch]
    for ch in public_part.upper():
        if ch not in _PUBLIC_LETTERS:
            raise InvalidAccessError(f"unrecognised public access letter '{ch}'")
        result |= _PUBLIC_LETTERS[ch]
    return result


def parse_access_spec(spec: str) -> Callable[[Access], Access]:
    """Compile an access spec into a transform on a file's current access.

    An **absolute** spec — ``"LWR/R"``, ``"WR/WR"``, ``"0x0B"``, ``"33"`` — is
    parsed by :func:`parse_access` and *replaces* the access wholesale, ignoring
    the current value.

    An **incremental** spec begins with ``+`` or ``-`` and edits the current
    value: a sequence of ``+letters`` / ``-letters`` clauses applied left to
    right. Each clause uses the same owner/public slash convention as the
    absolute form, so ``+L`` locks, ``-W`` removes owner write, ``+R/R`` adds
    owner and public read, ``-/R`` removes public read, and ``+L-W`` combines
    them. Incremental edits are idempotent (adding a set flag or removing a
    clear one is a no-op).

    The spec is validated *now*, so a malformed one raises
    :class:`~oaknut.file.exceptions.InvalidAccessError` immediately — even when
    the resulting transform is later applied to no files.
    """
    stripped = spec.strip()
    if stripped[:1] not in ("+", "-"):
        value = parse_access(stripped)
        return lambda _current: value

    operations = _parse_increments(stripped)

    def transform(current: Access) -> Access:
        result = current
        for add, flags in operations:
            result = (result | flags) if add else (result & ~flags)
        return result

    return transform


def _parse_increments(spec: str) -> list[tuple[bool, Access]]:
    """Split an incremental spec into ``(is_add, flags)`` clauses, validated.

    *spec* is known to start with ``+`` or ``-``. Each clause runs from a
    ``+``/``-`` sign up to the next sign; an empty clause (a bare sign) is an
    error, as is any unrecognised letter.
    """
    operations: list[tuple[bool, Access]] = []
    i, n = 0, len(spec)
    while i < n:
        add = spec[i] == "+"
        j = i + 1
        while j < n and spec[j] not in "+-":
            j += 1
        letters = spec[i + 1 : j]
        if not letters:
            raise InvalidAccessError(f"empty '{spec[i]}' operation in access spec {spec!r}")
        operations.append((add, _parse_letters(letters)))
        i = j
    return operations


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
    if attr & Access.X:
        owner += "X"

    public = ""
    if attr & Access.PW:
        public += "W"
    if attr & Access.PR:
        public += "R"

    return f"{owner}/{public}"

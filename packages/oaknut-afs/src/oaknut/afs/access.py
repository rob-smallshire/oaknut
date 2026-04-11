"""AFS on-disc access byte.

The Level 3 File Server stores an object's access attributes in a
single byte at offset 20 of its directory entry (see
``docs/afs-onwire.md`` §Directory entry). The bit layout **differs**
from the standard Acorn attribute byte used by client-side NFS/ANFS
clients and by ``oaknut.file.Access``. Per ``Uade01.asm:257-275`` and
Beebmaster's PDF:

====  =========================
Bit   Meaning
====  =========================
0     Public read
1     Public write
2     Owner read
3     Owner write
4     Locked
5     Directory type (1 = dir)
6-7   Unused on disc
====  =========================

Masks from the ROM:

- ``ACCMSK = 0x1F`` — bits 0–4 (locked + all R/W bits)
- ``TLAMSK = 0x3F`` — type + locked + all R/W bits
- ``RWMSK  = 0x0F`` — owner + public R/W only

The access string form used by Econet clients (``"LR/WR"``, ``"LWR/R"``,
``"D/"``, etc.) is the same form users see in ``*EX`` listings and is
documented in the Beebmaster PDF's "Example Access Strings" table. This
module parses and formats that string.

Conversions to and from the wire-format ``oaknut.file.Access`` (which
uses a different bit layout) are provided so that ``host_bridge``
metadata round-trips correctly.
"""

from __future__ import annotations

from enum import IntFlag

# ---------------------------------------------------------------------------
# Bit positions — the on-disc layout.
# ---------------------------------------------------------------------------

_BIT_PUBLIC_READ = 0x01
_BIT_PUBLIC_WRITE = 0x02
_BIT_OWNER_READ = 0x04
_BIT_OWNER_WRITE = 0x08
_BIT_LOCKED = 0x10
_BIT_DIRECTORY = 0x20


class AFSAccess(IntFlag):
    """On-disc AFS access byte.

    The integer value of any combination is the byte stored in the
    ``DRACCS`` field of a directory entry — it may be written straight
    into a ``SectorsView`` without further translation::

        entry_bytes[20] = int(AFSAccess.from_string("LR/R"))

    Composable with ``|``::

        AFSAccess.OWNER_READ | AFSAccess.OWNER_WRITE | AFSAccess.PUBLIC_READ
    """

    PUBLIC_READ = _BIT_PUBLIC_READ
    PUBLIC_WRITE = _BIT_PUBLIC_WRITE
    OWNER_READ = _BIT_OWNER_READ
    OWNER_WRITE = _BIT_OWNER_WRITE
    LOCKED = _BIT_LOCKED
    DIRECTORY = _BIT_DIRECTORY

    @classmethod
    def from_byte(cls, value: int) -> AFSAccess:
        """Build an ``AFSAccess`` from a raw access byte.

        Unknown bits (6 and 7) are silently ignored, matching the
        server's tolerance for junk in the unused bits.
        """
        return cls(value & 0x3F)

    def to_byte(self) -> int:
        """Return the raw access byte suitable for on-disc storage."""
        return int(self) & 0x3F

    # -----------------------------------------------------------------
    # String form — "LWR/WR" style
    # -----------------------------------------------------------------

    def to_string(self) -> str:
        """Format as the human-readable ``"owner/public"`` string.

        Directory objects render as ``"D/"`` or ``"DL/"`` — consistent
        with the server's ``*EX`` listings and with the Beebmaster PDF.
        """
        if self & AFSAccess.DIRECTORY:
            owner = "D"
            if self & AFSAccess.LOCKED:
                owner += "L"
            return f"{owner}/"

        owner = ""
        if self & AFSAccess.LOCKED:
            owner += "L"
        if self & AFSAccess.OWNER_WRITE:
            owner += "W"
        if self & AFSAccess.OWNER_READ:
            owner += "R"

        public = ""
        if self & AFSAccess.PUBLIC_WRITE:
            public += "W"
        if self & AFSAccess.PUBLIC_READ:
            public += "R"

        return f"{owner}/{public}"

    @classmethod
    def from_string(cls, text: str) -> AFSAccess:
        """Parse an ``"owner/public"`` access string.

        Accepts the forms in the Beebmaster PDF's "Example Access
        Strings" table:

        - ``"/"`` — no access at all (byte 0x00)
        - ``"L/"`` — locked, otherwise no access
        - ``"LR/R"``, ``"LWR/WR"``, ``"WR/R"``, ``"R/"`` …
        - ``"D/"``, ``"DL/"`` — directories (the access bits are ignored
          for directories per the PDF; the server only honours locked)

        Letters may appear in any order within each side, but the
        forward slash is mandatory. Upper/lower case is accepted;
        whitespace is not.
        """
        if "/" not in text:
            raise ValueError(f"AFSAccess.from_string: missing '/' in {text!r}")

        owner, public = text.split("/", 1)
        owner = owner.upper()
        public = public.upper()

        result = cls(0)

        # Directory: the 'D' prefix is recognised even though directories
        # don't strictly use the R/W bits.
        if "D" in owner:
            result |= cls.DIRECTORY
            # Directories may only be locked or unlocked; the server
            # ignores R/W on a directory.
            if "L" in owner:
                result |= cls.LOCKED
            _reject_unexpected(owner, "DL", text)
            if public:
                raise ValueError(
                    f"AFSAccess.from_string: directories take no public access bits, got {text!r}"
                )
            return result

        # File access.
        if "L" in owner:
            result |= cls.LOCKED
        if "W" in owner:
            result |= cls.OWNER_WRITE
        if "R" in owner:
            result |= cls.OWNER_READ
        _reject_unexpected(owner, "LWR", text)

        if "W" in public:
            result |= cls.PUBLIC_WRITE
        if "R" in public:
            result |= cls.PUBLIC_READ
        _reject_unexpected(public, "WR", text)

        return result

    # -----------------------------------------------------------------
    # Type-checking helpers
    # -----------------------------------------------------------------

    @property
    def is_directory(self) -> bool:
        return bool(self & AFSAccess.DIRECTORY)

    @property
    def is_locked(self) -> bool:
        return bool(self & AFSAccess.LOCKED)


def _reject_unexpected(segment: str, allowed: str, original: str) -> None:
    allowed_set = set(allowed)
    unexpected = [c for c in segment if c not in allowed_set]
    if unexpected:
        raise ValueError(
            f"AFSAccess.from_string: unexpected character(s) "
            f"{''.join(unexpected)!r} in {original!r} (allowed: {allowed!r})"
        )

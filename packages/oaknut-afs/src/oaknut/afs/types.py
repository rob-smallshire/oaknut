"""Domain value types for oaknut.afs.

These are small, immutable value types that appear on the boundaries
between AFS modules. They exist chiefly for type-safety and readability:
a ``Sector`` is not interchangeable with a ``Cylinder``, and a
``SystemInternalName`` (SIN) should never be mistaken for a raw sector
address even though both are 24-bit integers.

All multi-byte integers on disc are little-endian (see
``docs/afs-onwire.md`` §Conventions). These types do **not** encode
byte order; they are pure integer wrappers.

References:
    Uade01.asm:254 — BLKSZE = &100 (256 bytes per sector).
    Uade02.asm:174-176, 193-205 — MPNOCY, MPSECS, MPSZNC etc.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import NewType

# ---------------------------------------------------------------------------
# Raw integer newtypes
# ---------------------------------------------------------------------------

#: A sector address within an AFS region, measured in 256-byte units
#: from the start of the physical disc. 24-bit.
Sector = NewType("Sector", int)

#: A cylinder index within an AFS region (0-based from the start of
#: the physical disc, not the start of the AFS region). 16-bit.
Cylinder = NewType("Cylinder", int)

#: System Internal Name — a 24-bit disc address pointing at the *map
#: sector* of an object, not at its data. Directory entries, info
#: sectors, and the allocator all deal in SINs.
SystemInternalName = NewType("SystemInternalName", int)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Geometry:
    """Physical geometry of the disc containing an AFS region.

    Attributes match the fields in the AFS info sector (see
    ``docs/afs-onwire.md`` §Info sector):

    - ``cylinders``: total cylinders on the physical disc (``MPSZNC``).
    - ``sectors_per_cylinder``: ``MPSZSC``.
    - ``total_sectors``: ``MPSZNS`` — 24-bit, so capped at 2^24.
    - ``bitmap_size_sectors``: ``MPSZSB`` — almost always 1.
    """

    cylinders: int
    sectors_per_cylinder: int
    total_sectors: int
    bitmap_size_sectors: int = 1

    def __post_init__(self) -> None:
        if self.cylinders <= 0:
            raise ValueError(f"cylinders must be positive, got {self.cylinders}")
        if self.sectors_per_cylinder <= 0:
            raise ValueError(
                f"sectors_per_cylinder must be positive, got {self.sectors_per_cylinder}"
            )
        if self.total_sectors <= 0:
            raise ValueError(f"total_sectors must be positive, got {self.total_sectors}")
        if self.total_sectors > 0xFFFFFF:
            # 24-bit field on disc (MPSZNS, 3 bytes)
            raise ValueError(f"total_sectors {self.total_sectors} exceeds 24-bit limit 0xFFFFFF")
        if self.bitmap_size_sectors < 1:
            raise ValueError(
                f"bitmap_size_sectors must be at least 1, got {self.bitmap_size_sectors}"
            )

    def cylinder_start_sector(self, cylinder: int) -> Sector:
        """Return the first (sector 0) of ``cylinder``."""
        return Sector(cylinder * self.sectors_per_cylinder)


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_BASE_YEAR = 1981  # Uade01.asm:207 — BASEYR = 81
# Year delta is 7 bits (4 bits at encoded[15:12], 3 bits at encoded[7:5]).
_MAX_YEAR_DELTA = 0x7F
_MAX_ENCODABLE_YEAR = _BASE_YEAR + _MAX_YEAR_DELTA


@dataclass(frozen=True, slots=True)
class AfsDate:
    """Packed 16-bit AFS creation date.

    The on-disc format is the Acorn file-server "RISC OS / old-format"
    date, stored little-endian as two bytes. The bit layout is:

    ======  =========================================================
    Bits    Field
    ======  =========================================================
     0-4    Day (1..31)
     5-7    High 3 bits of year delta
     8-11   Month (1..12)
    12-15   Low 4 bits of year delta
    ======  =========================================================

    where ``year_delta = year - 1981`` (so year 1981 has delta 0) and
    is a 7-bit value covering 1981..2108.

    This packing is equivalent to WFSINIT's formula (``WFSINIT.bas``
    line 4890 ff.)::

        encoded = ((year-81) * 4096)
                + (month * 256)
                + day
                + ((year-81) AND &F0) * 2
        stored = encoded AND &FFFF

    The high-nibble-shifted-left-1 term is how the low 4 bits of the
    year delta end up in bits 12-15 while the high 3 bits land in
    bits 5-7. WFSINIT lets the value overflow 16 bits; only the low
    16 bits are actually written. We mask explicitly for clarity.

    Verified against the Beebmaster PDF test disc: ``8/8/2010``
    round-trips to ``0xD828``.

    This class holds a Python ``datetime.date`` and (de)serialises on
    demand — we do *not* store the packed form, so every operation
    sees a plain date.
    """

    date: datetime.date

    def __post_init__(self) -> None:
        year = self.date.year
        if year < _BASE_YEAR or year > _MAX_ENCODABLE_YEAR:
            raise ValueError(
                f"year {year} is outside AFS encodable range [{_BASE_YEAR}, {_MAX_ENCODABLE_YEAR}]"
            )

    def to_bytes(self) -> bytes:
        """Encode as the 2-byte little-endian packed form."""
        year_delta = self.date.year - _BASE_YEAR
        encoded = (
            self.date.day
            | ((year_delta >> 4) & 0x07) << 5
            | (self.date.month & 0x0F) << 8
            | (year_delta & 0x0F) << 12
        )
        return (encoded & 0xFFFF).to_bytes(2, "little")

    @classmethod
    def from_bytes(cls, data: bytes) -> AfsDate:
        """Decode from the 2-byte little-endian packed form."""
        if len(data) != 2:
            raise ValueError(f"AfsDate.from_bytes requires 2 bytes, got {len(data)}")
        encoded = int.from_bytes(data, "little")
        day = encoded & 0x1F
        month = (encoded >> 8) & 0x0F
        year_delta = ((encoded >> 12) & 0x0F) | (((encoded >> 5) & 0x07) << 4)
        year = _BASE_YEAR + year_delta
        return cls(datetime.date(year, month, day))

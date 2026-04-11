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
_MAX_ENCODABLE_YEAR = _BASE_YEAR + 0xFF  # ((year-81) AND &FF) fits in byte-ish


@dataclass(frozen=True, slots=True)
class AfsDate:
    """Packed 16-bit AFS creation date.

    The on-disc format is the same as the Acorn file server date used
    by NFS clients:

    .. code::

        encoded = ((year - 1981) * 4096)
                + (month * 256)
                + day
                + ((year - 1981) & 0xF0) * 2

    The multiplication by 2 on the high nibble of the year offset is
    how the Acorn encoding squeezes an 8-bit year delta into the
    overlapping bit ranges of month and year. Years ≥ 2081 (offset
    ≥ 100) are not representable.

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
            (year_delta * 0x1000)
            + (self.date.month * 0x100)
            + self.date.day
            + ((year_delta & 0xF0) * 2)
        )
        return encoded.to_bytes(2, "little")

    @classmethod
    def from_bytes(cls, data: bytes) -> AfsDate:
        """Decode from the 2-byte little-endian packed form."""
        if len(data) != 2:
            raise ValueError(f"AfsDate.from_bytes requires 2 bytes, got {len(data)}")
        encoded = int.from_bytes(data, "little")
        day = encoded & 0x1F
        month = (encoded >> 8) & 0x0F
        # Recover year_delta from the two overlapping sources: the
        # low nibble of the high byte, plus the top bit of the low
        # byte (where the *2 shift lands).
        year_delta_low = (encoded >> 12) & 0x0F
        year_delta_high = (encoded >> 9) & 0x70  # recover the high nibble
        year_delta = year_delta_low | year_delta_high
        year = _BASE_YEAR + year_delta
        return cls(datetime.date(year, month, day))

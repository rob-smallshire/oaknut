"""Per-cylinder free-space bitmap.

Every cylinder in the AFS region stores a free-space bitmap in its
sector 0. Each bit represents one data sector of the same cylinder:

- Bit = 1 → sector is **free**
- Bit = 0 → sector is **allocated**

Sector number ``N`` lives at bit ``N & 7`` of byte ``N >> 3`` — that
is, sector 0 is bit 0 of byte 0 (the LSB), sector 7 is bit 7 of
byte 0 (the MSB), sector 8 is bit 0 of byte 1, and so on. See
Beebmaster's PDF page 7 ("Writing the Bit Maps") for the worked
example: a 16-sector cylinder with sectors 0 and 1 allocated gives
byte 0 = ``0xFC``, byte 1 = ``0xFF``.

The bitmap is stored as a single 256-byte sector (``MPSZSB = 1`` by
default), which caps the supported cylinder size at 2048 sectors.
Sector 0 of each cylinder is itself allocated (it is the bitmap),
so ``fresh()`` initialises with sector 0 clear and sectors 1..N-1 set.

This module provides two classes:

- :class:`CylinderBitmap` — an in-memory, self-contained bitmap for
  a single cylinder, indexed by local sector number (0..N-1).
- :class:`BitmapShadow` — a lazy cache of ``CylinderBitmap`` objects
  for every cylinder in an AFS region, with an in-memory per-cylinder
  free-count table for the allocator's "cylinder with most free space"
  query (phase 8). It reads bitmap sectors on demand via a callback
  and writes dirty bitmaps back on ``flush()``.

References:
    docs/afs-onwire.md §Bit map — the on-disc format.
    Uade02.asm:180 — MPSZCY, bit-map size in bytes.
    Uade02.asm:199 — MPSZSB, bit-map size in sectors.
    Uade01.asm:254 — BLKSZE = 256.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Iterator

BITMAP_SECTOR_SIZE = 256  # BLKSZE
MAX_SECTORS_PER_CYLINDER = BITMAP_SECTOR_SIZE * 8  # 2048


# ---------------------------------------------------------------------------
# CylinderBitmap
# ---------------------------------------------------------------------------


class CylinderBitmap:
    """In-memory bitmap for one cylinder's sectors.

    The bitmap knows its cylinder size (``sectors_per_cylinder``) so
    allocation queries can refuse out-of-range indices and iteration
    helpers cap themselves correctly. Bits beyond the cylinder size
    are always zero and cannot be written.
    """

    __slots__ = ("_data", "_spc")

    def __init__(
        self,
        sectors_per_cylinder: int,
        data: bytes | bytearray | None = None,
    ) -> None:
        if not (1 <= sectors_per_cylinder <= MAX_SECTORS_PER_CYLINDER):
            raise ValueError(
                f"sectors_per_cylinder {sectors_per_cylinder} outside 1..{MAX_SECTORS_PER_CYLINDER}"
            )
        self._spc = sectors_per_cylinder
        if data is None:
            self._data = bytearray(BITMAP_SECTOR_SIZE)
        else:
            if len(data) != BITMAP_SECTOR_SIZE:
                raise ValueError(f"bitmap data must be {BITMAP_SECTOR_SIZE} bytes, got {len(data)}")
            self._data = bytearray(data)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def fresh(cls, sectors_per_cylinder: int) -> CylinderBitmap:
        """Return a bitmap with sector 0 allocated and 1..N-1 free.

        Sector 0 is the bitmap sector itself and is always allocated.
        This matches the state that WFSINIT writes when initialising a
        new cylinder, modulo subsequent reservations (e.g. the two
        info sectors WFSINIT writes later clear bits 1 of the two
        relevant cylinders).
        """
        bitmap = cls(sectors_per_cylinder)
        for s in range(1, sectors_per_cylinder):
            bitmap.set_free(s)
        return bitmap

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def sectors_per_cylinder(self) -> int:
        return self._spc

    def _check(self, sector: int) -> None:
        if not (0 <= sector < self._spc):
            raise IndexError(f"sector {sector} outside cylinder range 0..{self._spc - 1}")

    def is_free(self, sector: int) -> bool:
        self._check(sector)
        return bool(self._data[sector >> 3] & (1 << (sector & 7)))

    def is_allocated(self, sector: int) -> bool:
        return not self.is_free(sector)

    def free_count(self) -> int:
        """Count free sectors in this cylinder.

        Only bits within ``[0, sectors_per_cylinder)`` are counted.
        Since :meth:`set_free` refuses out-of-range indices and
        :meth:`__init__` rejects bad input lengths, unused high bits
        are always zero and the sum works out correctly without a
        mask — but we still cap the count at ``sectors_per_cylinder``
        defensively in case a bitmap came from disc with stray high
        bits set.
        """
        # Fast path for cylinders whose size is a multiple of 8.
        if self._spc % 8 == 0:
            limit_byte = self._spc // 8
            return sum(bin(b).count("1") for b in self._data[:limit_byte])
        # General path: count partial last byte explicitly.
        whole_bytes = self._spc // 8
        count = sum(bin(b).count("1") for b in self._data[:whole_bytes])
        remainder = self._spc % 8
        mask = (1 << remainder) - 1
        count += bin(self._data[whole_bytes] & mask).count("1")
        return count

    def allocated_count(self) -> int:
        return self._spc - self.free_count()

    def find_first_free(self, start: int = 0) -> int | None:
        """Return the lowest free sector index ``>= start``, or ``None``.

        ``start`` may be outside the cylinder range; the function then
        returns ``None`` without raising, which is convenient for
        scan-to-end loops in the allocator.
        """
        if start >= self._spc:
            return None
        start = max(start, 0)
        for sector in range(start, self._spc):
            if self.is_free(sector):
                return sector
        return None

    def iter_free(self) -> Iterator[int]:
        """Yield every free sector index in ascending order."""
        for sector in range(self._spc):
            if self.is_free(sector):
                yield sector

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def set_free(self, sector: int) -> None:
        self._check(sector)
        self._data[sector >> 3] |= 1 << (sector & 7)

    def set_allocated(self, sector: int) -> None:
        self._check(sector)
        self._data[sector >> 3] &= ~(1 << (sector & 7)) & 0xFF

    def mark_range_allocated(self, start: int, length: int) -> None:
        """Mark ``length`` consecutive sectors allocated starting at ``start``.

        ``start`` must be within the cylinder; the range must not
        extend beyond ``sectors_per_cylinder``.
        """
        if length <= 0:
            raise ValueError(f"length must be positive, got {length}")
        end = start + length
        if end > self._spc:
            raise ValueError(f"range [{start}, {end}) extends beyond cylinder size {self._spc}")
        for sector in range(start, end):
            self.set_allocated(sector)

    def mark_range_free(self, start: int, length: int) -> None:
        """Mark ``length`` consecutive sectors free starting at ``start``."""
        if length <= 0:
            raise ValueError(f"length must be positive, got {length}")
        end = start + length
        if end > self._spc:
            raise ValueError(f"range [{start}, {end}) extends beyond cylinder size {self._spc}")
        for sector in range(start, end):
            self.set_free(sector)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Return the 256-byte on-disc bitmap sector."""
        return bytes(self._data)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CylinderBitmap):
            return NotImplemented
        return self._spc == other._spc and self._data == other._data

    def __repr__(self) -> str:
        return (
            f"CylinderBitmap(sectors_per_cylinder={self._spc}, "
            f"free={self.free_count()}/{self._spc})"
        )


# ---------------------------------------------------------------------------
# BitmapShadow
# ---------------------------------------------------------------------------


#: Callback signature for reading a cylinder's bitmap sector. The
#: callback is given a 0-based cylinder index (relative to the start
#: of the AFS region, **not** to the start of the physical disc) and
#: must return the 256-byte bitmap sector as raw bytes.
BitmapReader = Callable[[int], bytes]

#: Callback signature for writing a cylinder's bitmap sector.
BitmapWriter = Callable[[int, bytes], None]


class BitmapShadow:
    """Lazy cache of all cylinder bitmaps in an AFS region.

    On each ``bitmap_for(cylinder)`` call, the requested cylinder's
    bitmap is read from the underlying storage (via ``reader``) the
    first time it is touched and cached in memory thereafter.
    Mutating it through the returned :class:`CylinderBitmap` marks
    the cylinder dirty. ``flush()`` writes every dirty bitmap back
    through ``writer`` and clears the dirty set.

    Cylinder indices are **0-based relative to the start of the AFS
    region**. The caller (the allocator, phase 8) is responsible for
    translating those into physical cylinder numbers when calling the
    reader/writer.

    The shadow also maintains an in-memory ``free_count`` table
    mapping cylinder index to free-sector count. This gives the
    allocator O(1) "cylinder with most free space" queries without
    touching any bitmap byte. The count table is populated lazily
    from the first read of each cylinder.
    """

    def __init__(
        self,
        num_cylinders: int,
        sectors_per_cylinder: int,
        reader: BitmapReader,
        writer: BitmapWriter,
    ) -> None:
        if num_cylinders <= 0:
            raise ValueError(f"num_cylinders must be positive, got {num_cylinders}")
        self._num_cylinders = num_cylinders
        self._spc = sectors_per_cylinder
        self._reader = reader
        self._writer = writer
        self._cache: dict[int, CylinderBitmap] = {}
        self._free_counts: dict[int, int] = {}
        self._dirty: set[int] = set()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def num_cylinders(self) -> int:
        return self._num_cylinders

    @property
    def sectors_per_cylinder(self) -> int:
        return self._spc

    def _check(self, cylinder: int) -> None:
        if not (0 <= cylinder < self._num_cylinders):
            raise IndexError(
                f"cylinder {cylinder} outside AFS region range 0..{self._num_cylinders - 1}"
            )

    def bitmap_for(self, cylinder: int) -> CylinderBitmap:
        """Return the bitmap for ``cylinder``, reading it lazily."""
        self._check(cylinder)
        cached = self._cache.get(cylinder)
        if cached is not None:
            return cached
        raw = self._reader(cylinder)
        bitmap = CylinderBitmap(self._spc, raw)
        self._cache[cylinder] = bitmap
        self._free_counts[cylinder] = bitmap.free_count()
        return bitmap

    def free_count(self, cylinder: int) -> int:
        """Return the free-sector count for ``cylinder``.

        Reads the bitmap lazily on first access. Note this returns
        the count from the last time the bitmap was loaded or
        :meth:`refresh_free_count` was called — direct mutation of a
        ``CylinderBitmap`` does not update this cache automatically.
        Callers that mutate should call :meth:`refresh_free_count`
        or use :meth:`allocate_in`.
        """
        if cylinder not in self._free_counts:
            # Triggers a load.
            self.bitmap_for(cylinder)
        return self._free_counts[cylinder]

    def total_free(self) -> int:
        """Total free sectors across every cylinder.

        This forces a full scan of the AFS region on first call
        (every cylinder's bitmap is read), so the allocator should
        only use it when it genuinely needs the total — single-
        cylinder allocation lookups should use :meth:`free_count`.
        """
        for cylinder in range(self._num_cylinders):
            if cylinder not in self._free_counts:
                self.bitmap_for(cylinder)
        return sum(self._free_counts.values())

    def cylinder_with_most_free(self) -> int | None:
        """Return the cylinder index with the most free sectors.

        Triggers a full scan on first call for the same reason as
        :meth:`total_free`. Returns ``None`` if every cylinder is
        fully allocated.
        """
        for cylinder in range(self._num_cylinders):
            if cylinder not in self._free_counts:
                self.bitmap_for(cylinder)
        best_cylinder = None
        best_count = 0
        for cylinder, count in self._free_counts.items():
            if count > best_count:
                best_cylinder = cylinder
                best_count = count
        return best_cylinder

    # ------------------------------------------------------------------
    # Mutating operations that maintain the free-count cache
    # ------------------------------------------------------------------

    def mark_allocated(self, cylinder: int, sector: int) -> None:
        bitmap = self.bitmap_for(cylinder)
        if bitmap.is_allocated(sector):
            return
        bitmap.set_allocated(sector)
        self._free_counts[cylinder] -= 1
        self._dirty.add(cylinder)

    def mark_free(self, cylinder: int, sector: int) -> None:
        bitmap = self.bitmap_for(cylinder)
        if bitmap.is_free(sector):
            return
        bitmap.set_free(sector)
        self._free_counts[cylinder] += 1
        self._dirty.add(cylinder)

    def mark_range_allocated(self, cylinder: int, start: int, length: int) -> None:
        bitmap = self.bitmap_for(cylinder)
        bitmap.mark_range_allocated(start, length)
        self._free_counts[cylinder] = bitmap.free_count()
        self._dirty.add(cylinder)

    def mark_range_free(self, cylinder: int, start: int, length: int) -> None:
        bitmap = self.bitmap_for(cylinder)
        bitmap.mark_range_free(start, length)
        self._free_counts[cylinder] = bitmap.free_count()
        self._dirty.add(cylinder)

    def refresh_free_count(self, cylinder: int) -> None:
        """Re-count free sectors for ``cylinder`` from its bitmap.

        Call this after mutating a cylinder's :class:`CylinderBitmap`
        directly, if you bypassed the ``mark_*`` helpers above.
        """
        bitmap = self.bitmap_for(cylinder)
        self._free_counts[cylinder] = bitmap.free_count()
        self._dirty.add(cylinder)

    # ------------------------------------------------------------------
    # Flush
    # ------------------------------------------------------------------

    def dirty_cylinders(self) -> frozenset[int]:
        return frozenset(self._dirty)

    def flush(self) -> None:
        """Write every dirty cylinder's bitmap back via ``writer``.

        After a successful flush the dirty set is empty but the cache
        is retained so later reads are still served from memory.
        """
        for cylinder in sorted(self._dirty):
            bitmap = self._cache[cylinder]
            self._writer(cylinder, bitmap.to_bytes())
        self._dirty.clear()

    def __repr__(self) -> str:
        return (
            f"BitmapShadow(num_cylinders={self._num_cylinders}, "
            f"cached={len(self._cache)}, dirty={len(self._dirty)})"
        )

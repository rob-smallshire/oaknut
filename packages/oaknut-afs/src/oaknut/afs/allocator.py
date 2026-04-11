"""MBBMCM-faithful sector allocator for AFS write paths.

This is the write-side counterpart to :class:`~oaknut.afs.bitmap.BitmapShadow`:
:class:`Allocator` allocates one or more data sectors from the free
space in an AFS region, producing a flat list of :class:`Extent`
values suitable for dropping into a :class:`~oaknut.afs.map_sector.MapSector`.
It also frees extents back to the bitmap shadow.

The policy matches the Level 3 File Server's MAPMAN allocator (not
MBBMCM — MBBMCM turns out to be the bit-map / map-block **cache**
manager, despite the briefing framing). The concrete references are:

- ``Uade10.asm:84-255`` ``MPCRSP`` — the "create space" entry point
  the server calls when a fresh object is being built. Computes the
  best cylinder via ``FNDCY``, allocates a root map block via
  ``ALBLK``, then allocates data extents via ``ABLKS`` / ``FLBLKS``
  and writes the JesMap header including BILB.
- ``Uade11.asm:916-980`` ``FNDCY`` — "find cylinder": walks the
  in-memory per-cylinder free-count table ``MPCYMP`` and returns
  the cylinder with the **largest** free-sector count. Implements
  a best-fit-by-free-count cylinder picker; no rotating cursor,
  no locality bias.
- ``Uade12.asm:520-622`` ``ALBLK`` — "allocate one block": scans a
  cylinder's bitmap starting at bit 0 of byte 0 upward, returning
  the first free sector it encounters. First-fit, low-bit-first.
- ``Uade12.asm:640``+ ``ABLKS`` — "allocate multiple sectors from
  one cylinder": calls ``ALBLK`` repeatedly until the cylinder is
  drained or the request is satisfied. Adjacent sectors naturally
  coalesce into a single extent.
- ``Uade11.asm:1077``+ ``FLBLKS`` — "fill blocks across cylinders":
  when one cylinder runs out and more is still needed, walks the
  next-best cylinder and continues. Fragmentation across cylinders
  is allowed; the map block stores one extent per contiguous run.
- ``Uade12.asm:891``+ ``DAGRP`` — deallocate a data extent: sets
  the cleared bits in the appropriate cylinder's bitmap, decrements
  the cylinder's free-count, marks the bitmap dirty via ``MBMWT``.
- ``Uade12.asm:1116``+ ``CLRBLK`` — walks an object's entire map
  chain, deallocating each data extent via ``DAGRP`` and freeing
  the map block sector itself after all extents are released.

The Python implementation differs from the ROM in one respect that
does **not** affect correctness but does affect on-disc byte
equivalence: the allocator here scans each cylinder in one pass,
producing coalesced extents directly (longest contiguous free run
from the first free bit, then the next, etc.), whereas the ROM
calls ``ALBLK`` once per sector and relies on the caller's extent
accumulator to merge neighbours. For a contiguous cylinder both
approaches yield the same extents; for a fragmented cylinder they
differ only in the order in which equal-sized extents are emitted.

Byte-exact WFSINIT matching is phase 20's problem (a
``wfsinit_compat`` mode the plan already earmarks as a private
test-only knob).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from oaknut.afs.bitmap import BitmapShadow
from oaknut.afs.exceptions import AFSInsufficientSpaceError
from oaknut.afs.map_sector import Extent
from oaknut.afs.types import Sector, SystemInternalName


@dataclass(frozen=True, slots=True)
class _SubAlloc:
    """One contiguous run allocated from a specific cylinder.

    Kept internally so the allocator can undo partial allocations if
    a multi-step request runs out of space mid-way.
    """

    cylinder_index: int  # 0-based relative to the AFS region
    start_in_cylinder: int
    length: int


class Allocator:
    """Policy layer over :class:`BitmapShadow`.

    Given the AFS region's ``start_cylinder`` (absolute, as recorded
    in the info sector) and its ``sectors_per_cylinder``, the
    allocator translates between cylinder-local bitmap coordinates
    and absolute disc sector numbers. All sector addresses exposed
    through the public API are **absolute** — the same values that
    go into a :class:`~oaknut.afs.map_sector.MapSector`'s extents
    and a :class:`~oaknut.afs.types.SystemInternalName`.
    """

    def __init__(
        self,
        shadow: BitmapShadow,
        *,
        start_cylinder: int,
        sectors_per_cylinder: int,
    ) -> None:
        if start_cylinder < 0:
            raise ValueError(f"start_cylinder must be non-negative, got {start_cylinder}")
        if sectors_per_cylinder <= 0:
            raise ValueError(
                f"sectors_per_cylinder must be positive, got {sectors_per_cylinder}"
            )
        if shadow.sectors_per_cylinder != sectors_per_cylinder:
            raise ValueError(
                f"shadow.sectors_per_cylinder ({shadow.sectors_per_cylinder}) "
                f"disagrees with sectors_per_cylinder ({sectors_per_cylinder})"
            )
        self._shadow = shadow
        self._start_cylinder = start_cylinder
        self._spc = sectors_per_cylinder

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def shadow(self) -> BitmapShadow:
        return self._shadow

    @property
    def start_cylinder(self) -> int:
        return self._start_cylinder

    @property
    def sectors_per_cylinder(self) -> int:
        return self._spc

    def total_free_sectors(self) -> int:
        """Sum of free sectors across every cylinder in the region."""
        return self._shadow.total_free()

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _absolute(self, cylinder_index: int, sector_in_cylinder: int) -> int:
        """Translate a (cylinder-index, sector-in-cylinder) pair to an
        absolute disc sector number."""
        return (self._start_cylinder + cylinder_index) * self._spc + sector_in_cylinder

    def _to_cylinder_coords(self, absolute_sector: int) -> tuple[int, int]:
        """Inverse of :meth:`_absolute`.

        Raises :class:`ValueError` if the sector falls outside the
        AFS region.
        """
        if absolute_sector < 0:
            raise ValueError(f"absolute sector {absolute_sector} is negative")
        cyl_abs, sec_in_cyl = divmod(absolute_sector, self._spc)
        cyl_index = cyl_abs - self._start_cylinder
        if cyl_index < 0 or cyl_index >= self._shadow.num_cylinders:
            raise ValueError(
                f"absolute sector {absolute_sector} is outside the AFS region "
                f"(cylinder {cyl_abs}, AFS starts at {self._start_cylinder})"
            )
        return cyl_index, sec_in_cyl

    # ------------------------------------------------------------------
    # Allocation
    # ------------------------------------------------------------------

    def allocate(self, num_sectors: int) -> list[Extent]:
        """Allocate ``num_sectors`` data sectors and return their extents.

        The returned extents cover exactly ``num_sectors`` sectors in
        total. Policy:

        - Cylinders are picked in descending free-count order (FNDCY).
        - Within a cylinder, contiguous free runs are taken from the
          lowest free sector upward (ALBLK first-fit).
        - If a single cylinder cannot satisfy the whole request, the
          allocator spills to successive cylinders by free-count
          (FLBLKS).
        - On failure (not enough total free space), every sub-allocation
          made during this call is rolled back before raising
          :class:`AFSInsufficientSpaceError`.

        ``num_sectors`` must be positive.
        """
        if num_sectors <= 0:
            raise ValueError(f"num_sectors must be positive, got {num_sectors}")

        subs: list[_SubAlloc] = []
        remaining = num_sectors
        visited: set[int] = set()

        try:
            while remaining > 0:
                cyl = self._pick_best_cylinder(exclude=visited)
                if cyl is None:
                    raise AFSInsufficientSpaceError(
                        f"not enough free space for {num_sectors} sectors "
                        f"(short by {remaining})"
                    )
                taken = self._drain_cylinder(cyl, remaining, subs)
                remaining -= taken
                if taken == 0:
                    # Defensive: if we couldn't take anything from a
                    # cylinder the picker said had space, refuse to
                    # loop forever.
                    visited.add(cyl)
                elif self._shadow.free_count(cyl) == 0:
                    visited.add(cyl)
        except Exception:
            self._rollback(subs)
            raise

        return [
            Extent(
                start=Sector(self._absolute(s.cylinder_index, s.start_in_cylinder)),
                length=s.length,
            )
            for s in subs
        ]

    def allocate_sector(self) -> SystemInternalName:
        """Allocate one sector and return its SIN.

        Convenience for map-block allocation: a JesMap map block
        occupies exactly one sector, and its SIN **is** that sector's
        absolute address. This is the ``ALBLK`` equivalent used by
        ``MPCRSP`` (``Uade10:168``) and by the chain-link path in
        ``MKRLN`` (``Uade12:187``).
        """
        extents = self.allocate(1)
        assert len(extents) == 1 and extents[0].length == 1
        return SystemInternalName(int(extents[0].start))

    # ------------------------------------------------------------------
    # Deallocation
    # ------------------------------------------------------------------

    def free_extent(self, extent: Extent) -> None:
        """Release ``extent`` back to the bitmap shadow.

        The extent may span multiple cylinders; the allocator splits
        it into per-cylinder chunks before updating the shadow.
        """
        if extent.length <= 0:
            raise ValueError(f"extent length must be positive, got {extent.length}")
        self._free_range(int(extent.start), extent.length)

    def free_extents(self, extents: list[Extent]) -> None:
        for extent in extents:
            self.free_extent(extent)

    def free_sector(self, sector: SystemInternalName | int) -> None:
        """Release a single sector (e.g. an obsolete map block).

        Equivalent to :meth:`free_extent` with length 1.
        """
        self._free_range(int(sector), 1)

    def _free_range(self, start: int, length: int) -> None:
        remaining = length
        cursor = start
        while remaining > 0:
            cyl_index, sec_in_cyl = self._to_cylinder_coords(cursor)
            room = self._spc - sec_in_cyl
            take = min(room, remaining)
            self._shadow.mark_range_free(cyl_index, sec_in_cyl, take)
            cursor += take
            remaining -= take

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _pick_best_cylinder(self, *, exclude: set[int]) -> Optional[int]:
        """Return the cylinder index with the most free sectors,
        excluding any in ``exclude``. Returns ``None`` if no cylinder
        has any free space left.

        Mirrors ``FNDCY`` (``Uade11:916-980``) but with exclusion
        — the ROM walks the full MPCYMP table on every call and
        doesn't need to skip cylinders, because ABLKS always manages
        to drain the cylinder it picks. Our path may not drain if
        the bitmap has oddities, so the exclusion set guards against
        an infinite loop.
        """
        best_cyl: Optional[int] = None
        best_count = 0
        for cyl in range(self._shadow.num_cylinders):
            if cyl in exclude:
                continue
            count = self._shadow.free_count(cyl)
            if count > best_count:
                best_cyl = cyl
                best_count = count
        return best_cyl

    def _drain_cylinder(
        self,
        cyl: int,
        max_sectors: int,
        subs: list[_SubAlloc],
    ) -> int:
        """Allocate up to ``max_sectors`` from cylinder ``cyl``.

        Scans the cylinder from sector 0 upward, taking each
        contiguous free run as a single sub-allocation and stopping
        when either ``max_sectors`` is satisfied or the cylinder has
        no more free bits. Returns the number of sectors actually
        taken (0 if nothing could be allocated).
        """
        bitmap = self._shadow.bitmap_for(cyl)
        taken = 0
        cursor = 0
        while taken < max_sectors and cursor < self._spc:
            run_start = bitmap.find_first_free(cursor)
            if run_start is None:
                break
            run_length = 0
            while (
                run_start + run_length < self._spc
                and bitmap.is_free(run_start + run_length)
                and taken + run_length < max_sectors
            ):
                run_length += 1
            if run_length == 0:
                break
            self._shadow.mark_range_allocated(cyl, run_start, run_length)
            subs.append(
                _SubAlloc(
                    cylinder_index=cyl,
                    start_in_cylinder=run_start,
                    length=run_length,
                )
            )
            taken += run_length
            cursor = run_start + run_length
        return taken

    def _rollback(self, subs: list[_SubAlloc]) -> None:
        """Release every sub-allocation in ``subs`` back to the shadow.

        Called when :meth:`allocate` fails partway through a
        multi-cylinder request. The shadow's per-cylinder free counts
        and dirty set are updated by :meth:`BitmapShadow.mark_range_free`.
        """
        for sub in subs:
            self._shadow.mark_range_free(
                sub.cylinder_index, sub.start_in_cylinder, sub.length
            )

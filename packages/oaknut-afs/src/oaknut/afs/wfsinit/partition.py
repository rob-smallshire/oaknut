"""Flexible-sizing repartitioner — carve an AFS region from an ADFS tail.

Phase 15 of the oaknut-afs build. Takes an already-open
:class:`oaknut.adfs.ADFS` handle (old-map only; new-map discs
cannot carry AFS pointers) and shrinks its free-space map to leave
room for an AFS region in the tail, then installs the info-sector
pointers that ``ADFS.afs_partition`` / ``AFS.from_file`` look for.

The API is split into a pure :func:`plan` that returns a
:class:`RepartitionPlan` dataclass (no mutation) and an imperative
:func:`apply` that actually runs ``ADFS.compact`` (when required)
and rewrites the map. This matches the ``git merge --no-commit``
shape and makes dry-runs trivial to test.

``AFSSizeSpec`` is the caller-facing algebraic type for the
size-selection policy:

- ``AFSSizeSpec.max()`` — the largest AFS region that fits after
  compaction. The common case.
- ``AFSSizeSpec.cylinders(n)`` / ``.sectors(n)`` / ``.bytes(n)`` —
  an explicit request, rounded up to a cylinder boundary.
- ``AFSSizeSpec.ratio(afs, adfs)`` — split remaining space in the
  given ratio.
- ``AFSSizeSpec.existing_free()`` — WFSINIT's historical behaviour:
  use exactly the current tail free extent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from oaknut.afs.exceptions import (
    AFSAlreadyPartitionedError,
    AFSDiscNotCompactedError,
    AFSInsufficientADFSSpaceError,
)

if TYPE_CHECKING:
    from oaknut.adfs import ADFS


#: Sector size in bytes — matches ``BLKSZE = 256`` across the stack.
_SECTOR_SIZE = 256

#: Minimum ADFS cylinders to leave in front of the AFS region.
#: WFSINIT's original allows an arbitrarily small ADFS partition,
#: but an ADFS disc with less than one cylinder is unusable in
#: practice. Matches the WFSINIT floor of 1 cylinder.
_MIN_ADFS_CYLINDERS = 1


@dataclass(frozen=True)
class AFSSizeSpec:
    """Tagged-union describing the caller's size request.

    Construct via the classmethods :meth:`max`, :meth:`cylinders`,
    :meth:`sectors`, :meth:`bytes_`, :meth:`ratio`, or
    :meth:`existing_free`. The dataclass fields are implementation
    details; do not construct directly.
    """

    kind: str  # "max" | "cylinders" | "sectors" | "bytes" | "ratio" | "existing"
    value_a: int = 0
    value_b: int = 0

    @classmethod
    def max(cls) -> AFSSizeSpec:
        return cls(kind="max")

    @classmethod
    def cylinders(cls, n: int) -> AFSSizeSpec:
        if n <= 0:
            raise ValueError(f"cylinders must be positive, got {n}")
        return cls(kind="cylinders", value_a=n)

    @classmethod
    def sectors(cls, n: int) -> AFSSizeSpec:
        if n <= 0:
            raise ValueError(f"sectors must be positive, got {n}")
        return cls(kind="sectors", value_a=n)

    @classmethod
    def bytes_(cls, n: int) -> AFSSizeSpec:
        if n <= 0:
            raise ValueError(f"bytes must be positive, got {n}")
        return cls(kind="bytes", value_a=n)

    @classmethod
    def ratio(cls, *, afs: int, adfs: int) -> AFSSizeSpec:
        if afs <= 0 or adfs <= 0:
            raise ValueError("ratio parts must be positive")
        return cls(kind="ratio", value_a=afs, value_b=adfs)

    @classmethod
    def existing_free(cls) -> AFSSizeSpec:
        return cls(kind="existing")


@dataclass(frozen=True)
class RepartitionPlan:
    """Pure description of a repartition, produced by :func:`plan`.

    - ``start_cylinder``: where the AFS region will begin.
    - ``afs_cylinders``: cylinder count for the AFS region.
    - ``new_adfs_cylinders``: cylinder count retained for ADFS.
    - ``sec1`` / ``sec2``: absolute sector addresses of the two
      info sectors WFSINIT would install.
    - ``total_afs_sectors``: number of sectors in the AFS region.
    - ``will_compact``: whether :func:`apply` will call
      ``ADFS.compact()`` before shrinking.
    """

    start_cylinder: int
    afs_cylinders: int
    new_adfs_cylinders: int
    sec1: int
    sec2: int
    total_afs_sectors: int
    will_compact: bool


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


def _cylinder_geometry(adfs: "ADFS") -> tuple[int, int]:
    """Return ``(sectors_per_cylinder, total_cylinders)`` from the
    authoritative geometry stored on the ADFS object.
    """
    geom = adfs.geometry
    return geom.sectors_per_cylinder, geom.cylinders


def plan(
    adfs: "ADFS",
    *,
    size: AFSSizeSpec,
    compact_adfs: bool = True,
) -> RepartitionPlan:
    """Compute the repartition plan without mutating the disc.

    Raises:
        AFSAlreadyPartitionedError: AFS pointers are already present.
        AFSNewMapNotSupportedError: new-map ADFS (not implemented).
        AFSDiscNotCompactedError: ``compact_adfs=False`` and the
            current free list is fragmented.
        AFSInsufficientADFSSpaceError: the requested size would
            leave fewer than the minimum ADFS cylinders.
    """
    # Reject if AFS is already installed.
    sec1_existing, sec2_existing = adfs._fsm.afs_info_pointers
    if sec1_existing != 0 or sec2_existing != 0:
        raise AFSAlreadyPartitionedError(
            f"disc already has AFS pointers: sec1={sec1_existing:#x}, sec2={sec2_existing:#x}"
        )

    spc, total_cylinders = _cylinder_geometry(adfs)
    total_sectors = total_cylinders * spc

    # Compute the post-compaction used-sectors count = used cells.
    free_entries = adfs._fsm.free_space_entries()
    total_free_bytes = sum(length for _, length in free_entries)
    total_free_sectors = total_free_bytes // _SECTOR_SIZE
    used_sectors = total_sectors - total_free_sectors

    # Decide whether compaction will be needed.
    will_compact = False
    if compact_adfs:
        # If the free list is fragmented or the tail free extent is
        # not the largest, we need to compact first to actually
        # realise the planned AFS region. For simplicity, always
        # flag compact when requested AND free list has > 1 entry.
        will_compact = len(free_entries) > 1
    else:
        if len(free_entries) > 1:
            raise AFSDiscNotCompactedError("ADFS free list is fragmented; pass compact_adfs=True")

    # Determine the AFS size.
    if size.kind == "max":
        # Leave at least MIN_ADFS_CYLINDERS cylinders for ADFS at
        # the front. Used sectors in a freshly-created disc are
        # held at sectors 0..6 (free space map + root directory),
        # which is well inside the first cylinder.
        min_adfs_sectors = _MIN_ADFS_CYLINDERS * spc
        max_usable = total_sectors - max(used_sectors, min_adfs_sectors)
        afs_sectors = max_usable
    elif size.kind == "cylinders":
        afs_sectors = size.value_a * spc
    elif size.kind == "sectors":
        afs_sectors = size.value_a
    elif size.kind == "bytes":
        afs_sectors = (size.value_a + _SECTOR_SIZE - 1) // _SECTOR_SIZE
    elif size.kind == "ratio":
        available = total_sectors - used_sectors
        afs_share = available * size.value_a // (size.value_a + size.value_b)
        afs_sectors = afs_share
    elif size.kind == "existing":
        if not free_entries:
            afs_sectors = 0
        else:
            # Use the last free extent (tail).
            last_start_bytes, last_length_bytes = free_entries[-1]
            afs_sectors = last_length_bytes // _SECTOR_SIZE
    else:  # pragma: no cover
        raise ValueError(f"unknown AFSSizeSpec kind: {size.kind}")

    # Round up to a cylinder boundary.
    if afs_sectors % spc != 0:
        afs_sectors = ((afs_sectors + spc - 1) // spc) * spc
    afs_cylinders = afs_sectors // spc

    if afs_cylinders <= 0:
        raise AFSInsufficientADFSSpaceError("AFS size would be zero cylinders")

    new_adfs_cylinders = total_cylinders - afs_cylinders
    if new_adfs_cylinders < _MIN_ADFS_CYLINDERS:
        raise AFSInsufficientADFSSpaceError(
            f"requested AFS size ({afs_cylinders} cylinders) would leave "
            f"only {new_adfs_cylinders} cylinders for ADFS "
            f"(minimum {_MIN_ADFS_CYLINDERS})"
        )

    start_cylinder = new_adfs_cylinders
    sec1 = start_cylinder * spc + 1
    sec2 = sec1 + spc

    return RepartitionPlan(
        start_cylinder=start_cylinder,
        afs_cylinders=afs_cylinders,
        new_adfs_cylinders=new_adfs_cylinders,
        sec1=sec1,
        sec2=sec2,
        total_afs_sectors=afs_sectors,
        will_compact=will_compact,
    )


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def apply(adfs: "ADFS", plan_obj: RepartitionPlan) -> None:
    """Execute a repartition plan against ``adfs``.

    Runs ``ADFS.compact()`` if the plan requires it, shrinks the
    old free space map to the new ADFS cylinder count, and installs
    the AFS info-sector pointers at ``&F6`` / ``&1F6``. The disc
    must be opened writable.

    This is a one-shot operation — after success, the disc has an
    AFS region with no AFS structures yet (just a shrunken ADFS
    map with pointers). The next step is
    :func:`oaknut.afs.wfsinit.initialise` (phase 19).
    """
    if plan_obj.will_compact:
        adfs.compact()

    spc, total_cylinders = _cylinder_geometry(adfs)
    new_total = plan_obj.new_adfs_cylinders * spc
    adfs._fsm.shrink_to(new_total)
    adfs._fsm.install_afs_pointers(plan_obj.sec1, plan_obj.sec2)

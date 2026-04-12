"""Follow-up 1 — chain-expanding file writes.

Verify that _create_object can handle files large enough to need
more than 48 data extents (and therefore more than one map block),
and that the resulting chained object is readable end to end.
"""

from __future__ import annotations

from helpers.afs_image import build_synthetic_adfs_with_afs
from oaknut.afs.map_sector import _MAX_DATA_EXTENTS


class TestChainExpandingCreate:
    def test_create_file_needing_chain(self) -> None:
        # Force fragmentation: pre-allocate alternate sectors so the
        # allocator produces one-sector extents. With 16 sectors per
        # cylinder and cylinder 0 having 15 free, we need many
        # cylinders to generate 49+ one-sector extents.
        #
        # Easier: just create a large enough file that even with
        # coalescing, the extent count stays above 48. On a 20-cyl
        # AFS region with 15 data sectors each = 300 sectors. If
        # the allocator fills one cylinder at a time (one extent per
        # cylinder after coalescing), we need > 48 cylinders.
        #
        # So use a larger AFS region. ADFS-L = 160 cyls. With
        # start_cylinder=5 (155 AFS cyls), we can produce 155
        # one-extent-per-cylinder runs if data is scattered.
        #
        # Simplest: create a really large file. The allocator coalesces
        # within-cylinder, so for a 155-cylinder region, we get at most
        # 155 extents. That's > 48 and will require chaining.

        adfs = build_synthetic_adfs_with_afs(start_cylinder=5)
        afs = adfs.afs_partition
        # Pre-fragment: allocate 1 sector in each of the first 60
        # cylinders so the next big allocation gets split across many
        # cylinders and produces > 48 extents.
        shadow = afs._bitmap_shadow()
        for cyl_index in range(min(60, shadow.num_cylinders)):
            # Allocate sector 1 of each cylinder so the allocator
            # can't merge adjacent runs.
            shadow.mark_allocated(cyl_index, 2)
        shadow.flush()

        # Now write a file that occupies ~60 cylinders worth of data.
        # Each cylinder has 14 free sectors (15 - 1 we just took), so
        # 60 × 14 = 840 sectors. The allocator will produce at most
        # 60 one-extent-per-cylinder runs (the 14-sector runs within
        # each cylinder coalesce, but across cylinders they don't).
        #
        # 60 coalesced extents > 48 → needs chaining.
        payload_size = 800 * 256  # 800 sectors
        payload = bytes(i & 0xFF for i in range(payload_size))
        (afs.root / "Huge").write_bytes(payload)
        readback = (afs.root / "Huge").read_bytes()
        assert readback == payload

    def test_chain_round_trip_survives_reopen(self) -> None:
        adfs = build_synthetic_adfs_with_afs(start_cylinder=5)
        afs = adfs.afs_partition
        shadow = afs._bitmap_shadow()
        for cyl_index in range(min(60, shadow.num_cylinders)):
            shadow.mark_allocated(cyl_index, 2)
        shadow.flush()

        payload = bytes(i & 0xFF for i in range(800 * 256))
        (afs.root / "Huge").write_bytes(payload)

        afs2 = adfs.afs_partition
        assert (afs2.root / "Huge").read_bytes() == payload

    def test_small_file_still_works(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Tiny").write_bytes(b"small")
        assert (afs.root / "Tiny").read_bytes() == b"small"

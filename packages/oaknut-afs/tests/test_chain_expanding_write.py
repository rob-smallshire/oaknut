"""Follow-up 1 — chain-expanding file writes.

Verify that _create_object can handle files large enough to need
more than 48 data extents (and therefore more than one map block),
and that the resulting chained object is readable end to end.
"""

from __future__ import annotations

from helpers.afs_image import build_synthetic_adfs_with_afs
from oaknut.afs.map_sector import _MAX_DATA_EXTENTS, MAGIC


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
        afs.flush()

        afs2 = adfs.afs_partition
        assert (afs2.root / "Huge").read_bytes() == payload

    def test_small_file_still_works(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Tiny").write_bytes(b"small")
        assert (afs.root / "Tiny").read_bytes() == b"small"


class TestChainOnDiscByteShape:
    """The bytes that hit disc for a multi-block chain must match the
    ROM layout: ``'JesMap'`` at offset 0 of the head block, zeros at
    offset 0..5 of every successor block. See ``Uade10:235-242``
    (MPCRSP, the only magic-write site) and ``Uade12:160-242``
    (MKRLN, which allocates successors via ``ALBLK`` + ``CLRSTR`` and
    never overwrites bytes 0..5).
    """

    def _fragment_and_write_chained_file(self):
        # Pre-fragment so the allocator is forced into >48 coalesced
        # extents. Each AFS cylinder has 31 data sectors (32 minus the
        # bitmap sector). Marking sectors 4, 8, 12, 16, 20, 24, 28
        # across every available cylinder forces the cylinder's free
        # space into ~8 short runs, so a file consuming the whole AFS
        # region will need many extents.
        adfs = build_synthetic_adfs_with_afs(start_cylinder=5)
        afs = adfs.afs_partition
        shadow = afs._bitmap_shadow()
        for cyl_index in range(shadow.num_cylinders):
            for marker in (4, 8, 12, 16, 20, 24, 28):
                shadow.mark_allocated(cyl_index, marker)
        shadow.flush()
        # Pick a payload large enough that the allocator visits enough
        # cylinders to overflow 48 extents.
        payload = bytes(i & 0xFF for i in range(400 * 256))
        (afs.root / "Huge").write_bytes(payload)
        afs.flush()
        return adfs, afs

    def test_head_block_has_magic_successors_do_not(self) -> None:
        adfs, afs = self._fragment_and_write_chained_file()
        _, entry = afs._resolve(afs.root / "Huge")
        chain = afs._read_map_chain(entry.sin)
        assert len(chain.blocks) >= 2, (
            f"expected a chained file; got {len(chain.blocks)} block(s)"
        )

        head_raw = afs._read_sector(int(chain.blocks[0].sin))
        assert head_raw[0:6] == MAGIC, (
            f"head block must carry the 'JesMap' magic; got {head_raw[0:6]!r}"
        )

        for i, block in enumerate(chain.blocks[1:], start=1):
            raw = afs._read_sector(int(block.sin))
            assert raw[0:6] == b"\x00" * 6, (
                f"successor block {i} (sin {int(block.sin):#x}) "
                f"must have zeros at offsets 0..5 to match ROM behaviour, "
                f"not {raw[0:6]!r}"
            )

    def test_chained_file_reopens_after_write(self) -> None:
        # The reader must accept the ROM-shaped successor blocks we
        # just wrote — i.e. MapChain.walk must parse successors with
        # is_head=False.
        adfs, afs = self._fragment_and_write_chained_file()
        afs.flush()
        afs2 = adfs.afs_partition
        readback = (afs2.root / "Huge").read_bytes()
        assert readback == bytes(i & 0xFF for i in range(400 * 256))

"""Tests for chained :class:`MapSector` reads (phase 7).

The server threads multi-block files via the 49th extent slot of each
map block: slot 48 (offset ``LSTENT = 250``) holds ``(next_block_SIN, 1)``
when there is a successor. A block with slot 48 == 0 is the final
block in its chain. See Uade12:187-227 (write) / Uade13:462-533 (read).

These tests build synthetic map block bytes directly and exercise:

- :meth:`MapSector.from_bytes` recognising the chain pointer.
- :meth:`MapSector.to_bytes` emitting it.
- :meth:`MapChain.walk` following the chain and flattening extents.
- :class:`ExtentStream` reading bytes across chain boundaries.
- The BILB field (``last_sector_bytes``) being picked up from the
  final block only.
"""

from __future__ import annotations

import pytest
from oaknut.afs import AFSBrokenMapError, SystemInternalName
from oaknut.afs.map_sector import (
    MAP_SECTOR_SIZE,
    Extent,
    ExtentStream,
    MapChain,
    MapSector,
)
from oaknut.afs.types import Sector


def _block(
    sin: int,
    extents: list[tuple[int, int]],
    *,
    next_sin: int | None = None,
    last_sector_bytes: int = 0,
    sequence_number: int = 0,
) -> MapSector:
    return MapSector(
        sin=SystemInternalName(sin),
        extents=tuple(Extent(Sector(s), n) for s, n in extents),
        last_sector_bytes=last_sector_bytes,
        sequence_number=sequence_number,
        next_sin=SystemInternalName(next_sin) if next_sin is not None else None,
    )


def _full_head(
    sin: int,
    *,
    start: int = 0x1000,
    next_sin: int,
) -> MapSector:
    """Build a head map block with all 48 data extents used and a chain
    pointer. The chain pointer is only reachable in a full block per
    the ROM's MPGSGB semantics, so test fixtures for multi-block
    chains must use this shape.
    """
    extents = [(start + i * 4, 1) for i in range(48)]
    return _block(sin, extents, next_sin=next_sin)


class TestMapSectorChainRoundTrip:
    def test_to_bytes_round_trip_with_chain_pointer(self) -> None:
        block = _full_head(0x100, next_sin=0x101)
        round_tripped = MapSector.from_bytes(block.to_bytes(), SystemInternalName(0x100))
        assert round_tripped == block

    def test_parse_without_chain_pointer(self) -> None:
        block = _block(0x100, [(0x200, 3)])
        round_tripped = MapSector.from_bytes(block.to_bytes(), SystemInternalName(0x100))
        assert round_tripped.next_sin is None
        assert round_tripped.is_last

    def test_chain_slot_length_is_one(self) -> None:
        block = _full_head(0x100, next_sin=0x101)
        raw = block.to_bytes()
        # LSTENT = 250; bytes 250..252 = next_sin LE, 253..254 = length = 1
        assert int.from_bytes(raw[250:253], "little") == 0x101
        assert int.from_bytes(raw[253:255], "little") == 1

    def test_chain_pointer_requires_full_block(self) -> None:
        with pytest.raises(ValueError, match="chain pointer at slot 48 is only reachable"):
            _block(0x100, [(0x200, 3)], next_sin=0x101)

    def test_last_sector_bytes_is_two_bytes_le(self) -> None:
        block = _block(0x100, [(0x200, 1)], last_sector_bytes=0xAA)
        raw = block.to_bytes()
        # BILB at offsets 8-9, little-endian. High byte must be zero
        # for a practical remainder of < 256.
        assert raw[8] == 0xAA
        assert raw[9] == 0x00

    def test_parse_with_high_byte_of_bilb(self) -> None:
        # Exercise the 16-bit BILB range even though real discs never
        # exceed 0xFF.
        block = _block(0x100, [(0x200, 1)], last_sector_bytes=0x0101)
        round_tripped = MapSector.from_bytes(block.to_bytes(), SystemInternalName(0x100))
        assert round_tripped.last_sector_bytes == 0x0101

    def test_48_data_extents_plus_chain_pointer_fit(self) -> None:
        extents = [(0x1000 + i * 4, 1) for i in range(48)]
        block = _block(0x100, extents, next_sin=0x101)
        raw = block.to_bytes()
        assert len(raw) == MAP_SECTOR_SIZE
        round_tripped = MapSector.from_bytes(raw, SystemInternalName(0x100))
        assert len(round_tripped.extents) == 48
        assert round_tripped.next_sin == 0x101


class TestMapChainWalk:
    def _make_chain_reader(self, blocks: dict[int, MapSector]):
        def reader(sin: SystemInternalName) -> MapSector:
            return blocks[int(sin)]
        return reader

    def test_single_block_chain(self) -> None:
        head = _block(0x100, [(0x200, 3)], last_sector_bytes=128)
        chain = MapChain.walk(SystemInternalName(0x100), self._make_chain_reader({0x100: head}))
        assert len(chain.blocks) == 1
        assert chain.last is head

    def test_two_block_chain_flattens_extents(self) -> None:
        head = _full_head(0x100, next_sin=0x101)
        tail = _block(0x101, [(0x9000, 3)], last_sector_bytes=17)
        chain = MapChain.walk(
            SystemInternalName(0x100),
            self._make_chain_reader({0x100: head, 0x101: tail}),
        )
        assert len(chain.blocks) == 2
        flat = chain.flat_extents()
        assert len(flat) == 48 + 1
        assert flat[-1] == Extent(Sector(0x9000), 3)

    def test_object_size_uses_final_block_bilb(self) -> None:
        # head block has a (stale) BILB of 99 that MUST be ignored;
        # only the tail block's BILB counts.
        head = MapSector(
            sin=SystemInternalName(0x100),
            extents=tuple(Extent(Sector(0x1000 + i * 4), 1) for i in range(48)),
            last_sector_bytes=99,
            next_sin=SystemInternalName(0x101),
        )
        tail = _block(0x101, [(0x9000, 3)], last_sector_bytes=50)
        chain = MapChain.walk(
            SystemInternalName(0x100),
            self._make_chain_reader({0x100: head, 0x101: tail}),
        )
        # total sectors = 48 + 3 = 51; last sector partial (50 bytes)
        assert chain.object_size_bytes() == 50 * 256 + 50

    def test_cycle_detection(self) -> None:
        a = _full_head(0x100, next_sin=0x101)
        b = _full_head(0x101, start=0x5000, next_sin=0x100)
        with pytest.raises(AFSBrokenMapError, match="cycle"):
            MapChain.walk(
                SystemInternalName(0x100),
                self._make_chain_reader({0x100: a, 0x101: b}),
            )

    def test_sector_at_offset_crosses_blocks(self) -> None:
        # Head block has 48 one-sector extents (logical sectors 0..47);
        # tail adds logical sectors 48..49.
        head = _full_head(0x100, next_sin=0x101)
        tail = _block(0x101, [(0x9000, 2)], last_sector_bytes=0)
        chain = MapChain.walk(
            SystemInternalName(0x100),
            self._make_chain_reader({0x100: head, 0x101: tail}),
        )
        # Byte 48*256 should land at the first sector of the tail block.
        sector, offset = chain.sector_at_offset(48 * 256)
        assert sector == 0x9000
        assert offset == 0


class TestExtentStreamAcrossChain:
    def test_read_crossing_block_boundary(self) -> None:
        # Head block has 48 single-sector extents (logical sectors 0..47);
        # tail block has a 2-sector extent (logical 48..49). Total = 50
        # sectors = 12800 bytes.
        head = _full_head(0x100, start=0x1000, next_sin=0x101)
        tail = _block(0x101, [(0x9000, 2)], last_sector_bytes=0)

        sectors: dict[int, bytes] = {}
        # Head block: 48 sectors at 0x1000, 0x1004, 0x1008, ...
        # Each one filled with a distinct byte pattern.
        for i in range(48):
            sectors[0x1000 + i * 4] = bytes((i,)) * 256
        sectors[0x9000] = b"X" * 256
        sectors[0x9001] = b"Y" * 256

        def sector_reader(sector: Sector) -> bytes:
            return sectors[int(sector)]

        chain = MapChain(blocks=(head, tail))
        stream = ExtentStream(chain, sector_reader)
        assert stream.size == 50 * 256

        # Read 4 bytes straddling the last head-block sector (47) and
        # the first tail-block sector (48): bytes [48*256 - 2, 48*256 + 2).
        data = stream.read(48 * 256 - 2, 4)
        assert data == bytes((47, 47)) + b"XX"

        # Full read of just the tail block's range.
        tail_bytes = stream.read(48 * 256, 2 * 256)
        assert tail_bytes == b"X" * 256 + b"Y" * 256

    def test_extent_stream_accepts_single_map_sector(self) -> None:
        # Backward-compat: passing a MapSector directly still works.
        block = _block(0x100, [(0x200, 1)], last_sector_bytes=10)

        def reader(sector: Sector) -> bytes:
            return b"x" * 256

        stream = ExtentStream(block, reader)
        assert stream.size == 10
        assert stream.read_all() == b"x" * 10

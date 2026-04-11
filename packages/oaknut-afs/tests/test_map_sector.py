"""Tests for oaknut.afs.map_sector.

Golden fixture is transcribed from Beebmaster's PDF pp.10-11: the
map sector of the Test Disc's root directory, at disc offset ``&7100``.
The PDF walks field-by-field through the decoding, giving us a
ready-made cross-check for our parser.
"""

from __future__ import annotations

import pytest
from helpers import beebmaster
from oaknut.afs import AFSBrokenMapError
from oaknut.afs.map_sector import (
    MAP_SECTOR_SIZE,
    Extent,
    ExtentStream,
    MapSector,
)
from oaknut.afs.types import Sector, SystemInternalName

# ---------------------------------------------------------------------------
# Beebmaster golden fixture — root directory map sector
# ---------------------------------------------------------------------------


class TestBeebmasterRootMap:
    """The PDF's p.11 worked example."""

    def _parse(self) -> MapSector:
        return MapSector.from_bytes(
            beebmaster.ROOT_MAP_SECTOR_BYTES,
            sin=SystemInternalName(beebmaster.ROOT_MAP_SECTOR_SIN),
        )

    def test_parses_without_error(self) -> None:
        self._parse()

    def test_single_extent(self) -> None:
        parsed = self._parse()
        assert len(parsed.extents) == 1

    def test_extent_start(self) -> None:
        parsed = self._parse()
        assert parsed.extents[0].start == beebmaster.ROOT_MAP_EXTENT_START

    def test_extent_length(self) -> None:
        parsed = self._parse()
        assert parsed.extents[0].length == beebmaster.ROOT_MAP_EXTENT_LENGTH

    def test_object_size(self) -> None:
        parsed = self._parse()
        assert parsed.object_size_bytes() == beebmaster.ROOT_MAP_OBJECT_SIZE_BYTES

    def test_sequence_number(self) -> None:
        parsed = self._parse()
        assert parsed.sequence_number == beebmaster.ROOT_MAP_SEQUENCE_NUMBER

    def test_round_trip_bytes(self) -> None:
        parsed = self._parse()
        assert parsed.to_bytes() == beebmaster.ROOT_MAP_SECTOR_BYTES


# ---------------------------------------------------------------------------
# Multi-extent synthetic fixtures
# ---------------------------------------------------------------------------


class TestMultipleExtents:
    def _sample(self) -> MapSector:
        return MapSector(
            sin=SystemInternalName(0x100),
            extents=(
                Extent(Sector(0x200), 3),
                Extent(Sector(0x400), 5),
                Extent(Sector(0x600), 2),
            ),
            last_sector_bytes=0,
        )

    def test_total_sectors(self) -> None:
        assert self._sample().total_sectors() == 10

    def test_object_size_exact(self) -> None:
        assert self._sample().object_size_bytes() == 10 * 256

    def test_round_trip(self) -> None:
        parsed = MapSector.from_bytes(
            self._sample().to_bytes(),
            sin=SystemInternalName(0x100),
        )
        assert parsed.extents == self._sample().extents

    def test_iter_sectors(self) -> None:
        sectors = list(self._sample().iter_sectors())
        expected = [
            0x200, 0x201, 0x202,
            0x400, 0x401, 0x402, 0x403, 0x404,
            0x600, 0x601,
        ]  # fmt: skip
        assert sectors == expected


class TestPartialLastSector:
    def _build(self, last_sector_bytes: int) -> MapSector:
        return MapSector(
            sin=SystemInternalName(0x100),
            extents=(Extent(Sector(0x200), 3),),
            last_sector_bytes=last_sector_bytes,
        )

    def test_exact_sectors(self) -> None:
        assert self._build(0).object_size_bytes() == 3 * 256

    def test_one_byte_in_last_sector(self) -> None:
        assert self._build(1).object_size_bytes() == 2 * 256 + 1

    def test_full_last_sector_minus_one(self) -> None:
        assert self._build(255).object_size_bytes() == 2 * 256 + 255


class TestEmptyObject:
    def test_size_zero(self) -> None:
        empty = MapSector(sin=SystemInternalName(0x100), extents=())
        assert empty.object_size_bytes() == 0

    def test_total_sectors_zero(self) -> None:
        empty = MapSector(sin=SystemInternalName(0x100), extents=())
        assert empty.total_sectors() == 0

    def test_iter_sectors_empty(self) -> None:
        empty = MapSector(sin=SystemInternalName(0x100), extents=())
        assert list(empty.iter_sectors()) == []


# ---------------------------------------------------------------------------
# Extent validation
# ---------------------------------------------------------------------------


class TestExtentValidation:
    def test_zero_start_rejected(self) -> None:
        with pytest.raises(ValueError, match="outside 1..0xFFFFFF"):
            Extent(Sector(0), 5)

    def test_zero_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="outside 1..0xFFFF"):
            Extent(Sector(0x100), 0)

    def test_oversize_start_rejected(self) -> None:
        with pytest.raises(ValueError):
            Extent(Sector(0x1000000), 1)

    def test_end_property(self) -> None:
        assert Extent(Sector(0x100), 4).end == 0x104


# ---------------------------------------------------------------------------
# Parse errors
# ---------------------------------------------------------------------------


class TestParseErrors:
    def test_wrong_length(self) -> None:
        with pytest.raises(AFSBrokenMapError, match="must be 256"):
            MapSector.from_bytes(b"\x00" * 10, sin=SystemInternalName(0x100))

    def test_bad_magic(self) -> None:
        raw = bytearray(beebmaster.ROOT_MAP_SECTOR_BYTES)
        raw[0] = ord("X")
        with pytest.raises(AFSBrokenMapError, match="bad map magic"):
            MapSector.from_bytes(
                bytes(raw),
                sin=SystemInternalName(beebmaster.ROOT_MAP_SECTOR_SIN),
            )

    def test_sequence_mismatch(self) -> None:
        raw = bytearray(beebmaster.ROOT_MAP_SECTOR_BYTES)
        raw[255] = 99  # trailing copy disagrees with leading 0
        with pytest.raises(AFSBrokenMapError, match="sequence-number mismatch"):
            MapSector.from_bytes(
                bytes(raw),
                sin=SystemInternalName(beebmaster.ROOT_MAP_SECTOR_SIN),
            )

    def test_nonzero_start_with_zero_length(self) -> None:
        raw = bytearray(MAP_SECTOR_SIZE)
        raw[0:6] = b"JesMap"
        # Single extent: start = 0x100, length = 0.
        raw[10:13] = (0x100).to_bytes(3, "little")
        raw[13:15] = (0).to_bytes(2, "little")
        with pytest.raises(AFSBrokenMapError, match="zero length"):
            MapSector.from_bytes(bytes(raw), sin=SystemInternalName(0x50))


# ---------------------------------------------------------------------------
# Maximum extent capacity
# ---------------------------------------------------------------------------


class TestMaxExtents:
    def test_49_extents_accepted(self) -> None:
        extents = tuple(Extent(Sector(0x100 + i * 10), 1) for i in range(49))
        map_sec = MapSector(
            sin=SystemInternalName(0x50),
            extents=extents,
        )
        assert len(map_sec.extents) == 49
        assert map_sec.total_sectors() == 49

    def test_50_extents_rejected(self) -> None:
        extents = tuple(Extent(Sector(0x100 + i * 10), 1) for i in range(50))
        with pytest.raises(ValueError, match="too many extents"):
            MapSector(sin=SystemInternalName(0x50), extents=extents)


# ---------------------------------------------------------------------------
# sector_at_offset
# ---------------------------------------------------------------------------


class TestSectorAtOffset:
    def _sample(self) -> MapSector:
        return MapSector(
            sin=SystemInternalName(0x100),
            extents=(
                Extent(Sector(0x200), 3),  # logical sectors 0, 1, 2
                Extent(Sector(0x400), 5),  # logical sectors 3, 4, 5, 6, 7
                Extent(Sector(0x600), 2),  # logical sectors 8, 9
            ),
            last_sector_bytes=100,
        )

    def test_first_byte(self) -> None:
        sector, off = self._sample().sector_at_offset(0)
        assert sector == 0x200
        assert off == 0

    def test_boundary_between_extents(self) -> None:
        # Byte 768 is the first byte of logical sector 3 = extent 2 start.
        sector, off = self._sample().sector_at_offset(3 * 256)
        assert sector == 0x400
        assert off == 0

    def test_middle_of_sector(self) -> None:
        sector, off = self._sample().sector_at_offset(3 * 256 + 100)
        assert sector == 0x400
        assert off == 100

    def test_last_byte_in_last_sector(self) -> None:
        # Object size = 9 * 256 + 100 = 2404 bytes, last valid offset 2403.
        sector, off = self._sample().sector_at_offset(2403)
        assert sector == 0x601
        assert off == 99

    def test_out_of_range_rejected(self) -> None:
        with pytest.raises(IndexError, match="past end"):
            self._sample().sector_at_offset(2404)

    def test_negative_rejected(self) -> None:
        with pytest.raises(IndexError, match="negative"):
            self._sample().sector_at_offset(-1)


# ---------------------------------------------------------------------------
# ExtentStream — whole-object read through a mock reader
# ---------------------------------------------------------------------------


class TestExtentStream:
    """Round-trip an object's bytes through the extent stream."""

    def _build_map_and_reader(self) -> tuple[MapSector, dict[int, bytes]]:
        """Three extents totalling 10 sectors with last_sector_bytes=100."""
        extents = (
            Extent(Sector(0x200), 3),
            Extent(Sector(0x400), 5),
            Extent(Sector(0x600), 2),
        )
        # Fill each sector with deterministic bytes so we can tell them apart.
        storage: dict[int, bytes] = {}
        for extent in extents:
            for sector in extent.iter_sectors():
                storage[int(sector)] = bytes([((int(sector) + i) & 0xFF) for i in range(256)])
        map_sec = MapSector(
            sin=SystemInternalName(0x100),
            extents=extents,
            last_sector_bytes=100,
        )
        return map_sec, storage

    def test_size(self) -> None:
        map_sec, storage = self._build_map_and_reader()
        stream = ExtentStream(map_sec, lambda s: storage[int(s)])
        assert stream.size == 9 * 256 + 100

    def test_read_all_length(self) -> None:
        map_sec, storage = self._build_map_and_reader()
        stream = ExtentStream(map_sec, lambda s: storage[int(s)])
        data = stream.read_all()
        assert len(data) == stream.size

    def test_read_all_content_first_sector(self) -> None:
        map_sec, storage = self._build_map_and_reader()
        stream = ExtentStream(map_sec, lambda s: storage[int(s)])
        data = stream.read_all()
        assert data[:256] == storage[0x200]

    def test_read_all_spans_extent_boundary(self) -> None:
        """The first byte of the second extent lands right after the first 3 sectors."""
        map_sec, storage = self._build_map_and_reader()
        stream = ExtentStream(map_sec, lambda s: storage[int(s)])
        data = stream.read_all()
        assert data[3 * 256] == storage[0x400][0]

    def test_read_all_final_sector_truncated(self) -> None:
        """Last sector contributes only last_sector_bytes bytes (100 here)."""
        map_sec, storage = self._build_map_and_reader()
        stream = ExtentStream(map_sec, lambda s: storage[int(s)])
        data = stream.read_all()
        assert data[-100:] == storage[0x601][:100]

    def test_partial_read(self) -> None:
        map_sec, storage = self._build_map_and_reader()
        stream = ExtentStream(map_sec, lambda s: storage[int(s)])
        # Read 50 bytes starting 10 into sector 1 of extent 1 (addr 0x201).
        offset = 1 * 256 + 10
        got = stream.read(offset, 50)
        assert got == storage[0x201][10:60]

    def test_read_crossing_sector(self) -> None:
        map_sec, storage = self._build_map_and_reader()
        stream = ExtentStream(map_sec, lambda s: storage[int(s)])
        # 250 bytes starting 100 into sector 0 → spills into sector 1.
        got = stream.read(100, 250)
        expected = storage[0x200][100:] + storage[0x201][:94]
        assert got == expected

    def test_out_of_range_read(self) -> None:
        map_sec, storage = self._build_map_and_reader()
        stream = ExtentStream(map_sec, lambda s: storage[int(s)])
        with pytest.raises(IndexError):
            stream.read(stream.size - 10, 20)

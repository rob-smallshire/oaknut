"""Tests for transparent reading of truncated disc images (GitHub issue #1, phase 1).

Truncated images are shorter than the canonical format size but still a
whole number of sectors.  They arise from tools like BeebAsm that omit
trailing empty sectors.
"""

import os
import sys
from pathlib import Path

import pytest

# conftest.py handles sys.path, but this file needs it too when run standalone
_TESTS_DIRPATH = Path(__file__).parent
_WORKSPACE_ROOT = _TESTS_DIRPATH.parent.parent.parent
for _path in (_TESTS_DIRPATH, _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from oaknut.dfs.dfs import DFS  # noqa: E402
from oaknut.dfs.formats import (  # noqa: E402
    ACORN_DFS_40T_SINGLE_SIDED,
    ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL,
    ACORN_DFS_80T_SINGLE_SIDED,
)

BYTES_PER_SECTOR = 256
SECTORS_PER_TRACK = 10
BYTES_PER_TRACK = BYTES_PER_SECTOR * SECTORS_PER_TRACK  # 2560


def _minimal_catalogue(buf, offset=0):
    """Write a minimal valid DFS catalogue into *buf* at *offset*.

    Sets an 8-character title across sectors 0 and 1, zero files, and
    a sector count of 200 (the minimum for a valid DFS catalogue that
    won't trip sanity checks).
    """
    buf[offset + 0 : offset + 8] = b"TRUNCATD"  # Title bytes 0-7
    buf[offset + 256 : offset + 260] = b"    "  # Title bytes 8-11
    buf[offset + 260] = 0  # Cycle number
    buf[offset + 261] = 0  # Number of files * 8 (0 files)
    buf[offset + 262] = 0x00  # High bits
    buf[offset + 263] = 200  # Sector count (low byte)


class TestFromBufferTruncated:
    """DFS.from_buffer should accept truncated but sector-aligned buffers."""

    def test_truncated_single_sided_80t_succeeds(self):
        """A 136-sector (34816-byte) buffer should be accepted as a
        truncated 80-track single-sided image.
        """
        truncated_size = 136 * BYTES_PER_SECTOR  # 34816
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)
        dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_SINGLE_SIDED)
        assert dfs.title == "TRUNCATD"

    def test_trailing_sectors_read_as_zeros(self):
        """Bytes beyond the original file extent should read as 0x00."""
        truncated_sectors = 20  # 2 tracks of data
        truncated_size = truncated_sectors * BYTES_PER_SECTOR
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)
        # Write recognisable data into the last physical sector
        last_sector_start = (truncated_sectors - 1) * BYTES_PER_SECTOR
        buf[last_sector_start : last_sector_start + 4] = b"\xDE\xAD\xBE\xEF"

        dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_SINGLE_SIDED)

        # The last physical sector should have our data
        surface = dfs._catalogued_surface._surface
        last_physical = surface.sector_range(truncated_sectors - 1, 1)
        assert bytes(last_physical[0:4]) == b"\xDE\xAD\xBE\xEF"

        # A sector beyond the physical extent should be all zeros
        beyond = surface.sector_range(truncated_sectors, 1)
        assert bytes(beyond[0:BYTES_PER_SECTOR]) == b"\x00" * BYTES_PER_SECTOR

    def test_single_track_image(self):
        """Even a single-track image (just the catalogue) should work."""
        one_track = BYTES_PER_TRACK
        buf = bytearray(one_track)
        _minimal_catalogue(buf)
        dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_SINGLE_SIDED)
        assert len(dfs.files) == 0

    def test_40t_truncated_succeeds(self):
        """Truncated 40-track single-sided image."""
        truncated_size = 50 * BYTES_PER_SECTOR  # 5 tracks
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)
        dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_40T_SINGLE_SIDED)
        assert dfs.title == "TRUNCATD"

    def test_full_size_still_works(self):
        """A full-size buffer should continue to work as before."""
        full_size = 80 * SECTORS_PER_TRACK * BYTES_PER_SECTOR  # 204800
        buf = bytearray(full_size)
        _minimal_catalogue(buf)
        dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_SINGLE_SIDED)
        assert dfs.title == "TRUNCATD"

    def test_interleaved_double_sided_truncated(self):
        """A truncated interleaved double-sided image should work for side 0."""
        # Interleaved: tracks alternate side0, side1, side0, side1...
        # 10 interleaved tracks = 5 tracks per side
        truncated_size = 10 * BYTES_PER_TRACK  # 25600
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)  # Side 0 catalogue at offset 0
        dfs = DFS.from_buffer(
            memoryview(buf), ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, side=0
        )
        assert dfs.title == "TRUNCATD"

    def test_sequential_double_sided_truncated(self):
        """A truncated sequential double-sided image should work for side 0."""
        # Sequential: all of side 0 first, then side 1
        # 50 tracks total — side 0 gets tracks 0..49 which is less than 80
        truncated_size = 50 * BYTES_PER_TRACK
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)
        dfs = DFS.from_buffer(
            memoryview(buf), ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL, side=0
        )
        assert dfs.title == "TRUNCATD"


class TestFromBufferRejection:
    """Buffers that are not sector-aligned or are otherwise invalid
    should still be rejected.
    """

    def test_not_sector_aligned_raises(self):
        """A buffer whose size is not a multiple of 256 should be rejected."""
        bad_size = 136 * BYTES_PER_SECTOR + 1  # 34817 — one byte over a boundary
        buf = bytearray(bad_size)
        _minimal_catalogue(buf)
        with pytest.raises(ValueError):
            DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_SINGLE_SIDED)

    def test_empty_buffer_raises(self):
        """A zero-length buffer should be rejected."""
        buf = bytearray(0)
        with pytest.raises(ValueError):
            DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_SINGLE_SIDED)


class TestFromFileTruncatedReadOnly:
    """DFS.from_file in read-only mode should pad in memory without
    modifying the original file.
    """

    def test_read_only_truncated_succeeds(self, tmp_path):
        """Opening a truncated .ssd read-only should succeed."""
        truncated_size = 136 * BYTES_PER_SECTOR
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        with DFS.from_file(filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            assert dfs.title == "TRUNCATD"
            assert len(dfs.files) == 0

    def test_read_only_does_not_modify_file(self, tmp_path):
        """The original file must not be modified by read-only access."""
        truncated_size = 136 * BYTES_PER_SECTOR
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        with DFS.from_file(filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            _ = dfs.title  # Force a read

        assert filepath.stat().st_size == truncated_size

    def test_trailing_sectors_read_as_zeros_from_file(self, tmp_path):
        """Padded region should read as zeros when opened from file."""
        truncated_sectors = 20
        truncated_size = truncated_sectors * BYTES_PER_SECTOR
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        with DFS.from_file(filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            surface = dfs._catalogued_surface._surface
            beyond = surface.sector_range(truncated_sectors, 1)
            assert bytes(beyond[0:BYTES_PER_SECTOR]) == b"\x00" * BYTES_PER_SECTOR


class TestFromFileTruncatedReadWrite:
    """DFS.from_file in read-write mode should extend the file to the
    canonical format size before mmapping.
    """

    def test_read_write_extends_file(self, tmp_path):
        """Opening a truncated .ssd read-write should extend the file."""
        truncated_size = 136 * BYTES_PER_SECTOR
        expected_size = 80 * SECTORS_PER_TRACK * BYTES_PER_SECTOR  # 204800
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        with DFS.from_file(filepath, ACORN_DFS_80T_SINGLE_SIDED, mode="r+b") as dfs:
            assert dfs.title == "TRUNCATD"

        assert filepath.stat().st_size == expected_size

    def test_read_write_extended_region_is_zeros(self, tmp_path):
        """The extended region should be filled with zeros."""
        truncated_size = 136 * BYTES_PER_SECTOR
        expected_size = 80 * SECTORS_PER_TRACK * BYTES_PER_SECTOR
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        with DFS.from_file(filepath, ACORN_DFS_80T_SINGLE_SIDED, mode="r+b"):
            pass

        data = filepath.read_bytes()
        assert data[truncated_size:] == b"\x00" * (expected_size - truncated_size)

    def test_read_write_preserves_original_data(self, tmp_path):
        """The original data in the truncated region must be preserved."""
        truncated_size = 136 * BYTES_PER_SECTOR
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)
        # Write a marker into the last sector of the original data
        marker_offset = truncated_size - BYTES_PER_SECTOR
        buf[marker_offset : marker_offset + 4] = b"\xCA\xFE\xBA\xBE"

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        with DFS.from_file(filepath, ACORN_DFS_80T_SINGLE_SIDED, mode="r+b"):
            pass

        data = filepath.read_bytes()
        assert data[marker_offset : marker_offset + 4] == b"\xCA\xFE\xBA\xBE"

    def test_read_write_full_size_not_modified(self, tmp_path):
        """A full-size image opened read-write should not change size."""
        full_size = 80 * SECTORS_PER_TRACK * BYTES_PER_SECTOR
        buf = bytearray(full_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "full.ssd"
        filepath.write_bytes(buf)

        with DFS.from_file(filepath, ACORN_DFS_80T_SINGLE_SIDED, mode="r+b") as dfs:
            _ = dfs.title

        assert filepath.stat().st_size == full_size

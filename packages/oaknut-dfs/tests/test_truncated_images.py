"""Tests for transparent reading of truncated disc images (GitHub issue #1).

Phase 1: from_buffer / from_file padding.
Phase 2: expand() function.

Truncated images are shorter than the canonical format size. They arise
from tools like BeebAsm that omit trailing empty sectors, and from
writers that trim the image to the last byte of the last file — which
leaves a *ragged* final sector, so the file is not even a whole number
of sectors. Both are tolerated: the short tail (whether whole trailing
sectors or a ragged fraction of one) is zero-filled up to the disc's
declared geometry. An SSD/DSD is a catalogue plus concatenated file
data, not an inherently sector-quantised container, so the physical
byte length carries no authority the catalogue does not.
"""

import sys
from pathlib import Path

import pytest

# conftest.py handles sys.path, but this file needs it too when run standalone
_TESTS_DIRPATH = Path(__file__).parent
_WORKSPACE_ROOT = _TESTS_DIRPATH.parent.parent.parent
for _path in (_TESTS_DIRPATH, _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from oaknut.dfs.dfs import DFS, expand  # noqa: E402
from oaknut.dfs.exceptions import InvalidFormatError  # noqa: E402
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
        buf[last_sector_start : last_sector_start + 4] = b"\xde\xad\xbe\xef"

        dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_SINGLE_SIDED)

        # The last physical sector should have our data
        surface = dfs._catalogued_surface._surface
        last_physical = surface.sector_range(truncated_sectors - 1, 1)
        assert bytes(last_physical[0:4]) == b"\xde\xad\xbe\xef"

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
        dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, side=0)
        assert dfs.title == "TRUNCATD"

    def test_sequential_double_sided_truncated(self):
        """A truncated sequential double-sided image should work for side 0."""
        # Sequential: all of side 0 first, then side 1
        # 50 tracks total — side 0 gets tracks 0..49 which is less than 80
        truncated_size = 50 * BYTES_PER_TRACK
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)
        dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL, side=0)
        assert dfs.title == "TRUNCATD"


class TestFromBufferRagged:
    """A buffer whose size is not a whole number of sectors — a writer
    that trimmed the image to the last byte of the last file — is padded
    up (its ragged final sector zero-filled) rather than rejected.
    """

    def test_not_sector_aligned_is_padded(self):
        """A buffer one byte past a sector boundary is accepted, not rejected."""
        ragged_size = 136 * BYTES_PER_SECTOR + 1  # 34817 — one byte over a boundary
        buf = bytearray(ragged_size)
        _minimal_catalogue(buf)
        dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_SINGLE_SIDED)
        assert dfs.title == "TRUNCATD"

    def test_ragged_tail_zero_filled_to_sector(self):
        """The ragged final sector reads as its bytes followed by zeros."""
        # 20 whole sectors of data plus a ragged 5 bytes of a 21st.
        ragged_size = 20 * BYTES_PER_SECTOR + 5
        buf = bytearray(ragged_size)
        _minimal_catalogue(buf)
        buf[20 * BYTES_PER_SECTOR : 20 * BYTES_PER_SECTOR + 5] = b"\x01\x02\x03\x04\x05"

        dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_SINGLE_SIDED)

        surface = dfs._catalogued_surface._surface
        sector20 = bytes(surface.sector_range(20, 1)[0:BYTES_PER_SECTOR])
        # The five real bytes survive; the rest of the sector is zero-filled.
        assert sector20[:5] == b"\x01\x02\x03\x04\x05"
        assert sector20[5:] == b"\x00" * (BYTES_PER_SECTOR - 5)

    def test_empty_buffer_raises_invalid_format(self):
        """A zero-length buffer is a format error, reported as a domain exception."""
        buf = bytearray(0)
        with pytest.raises(InvalidFormatError):
            DFS.from_buffer(memoryview(buf), ACORN_DFS_80T_SINGLE_SIDED)


class TestFromFileTruncated:
    """DFS.from_file in read-only mode should pad in memory without
    modifying the original file.
    """

    def test_truncated_open_succeeds(self, tmp_path):
        """Opening a truncated .ssd should succeed (in-memory padding)."""
        truncated_size = 136 * BYTES_PER_SECTOR
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        with DFS.from_file(filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            assert dfs.title == "TRUNCATD"
            assert len(dfs.files) == 0

    def test_open_does_not_modify_file(self, tmp_path):
        """Opening a truncated file must not modify it on disc."""
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


# DFS.from_file never extends a truncated image on open — opening
# never modifies the file. The explicit way to grow a truncated
# image to its canonical size is :func:`expand`, exercised below.


# ===================================================================
# Phase 2: expand() function
# ===================================================================


class TestExpand:
    """expand() physically extends a truncated image file on disc."""

    def test_expand_truncated_image(self, tmp_path):
        """A truncated image should be extended to the canonical size."""
        truncated_size = 136 * BYTES_PER_SECTOR
        expected_size = 80 * SECTORS_PER_TRACK * BYTES_PER_SECTOR  # 204800
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        bytes_added = expand(filepath, ACORN_DFS_80T_SINGLE_SIDED)

        assert filepath.stat().st_size == expected_size
        assert bytes_added == expected_size - truncated_size

    def test_expand_preserves_original_data(self, tmp_path):
        """Original data must be preserved after expansion."""
        truncated_size = 20 * BYTES_PER_SECTOR
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)
        buf[-4:] = b"\xde\xad\xbe\xef"

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        expand(filepath, ACORN_DFS_80T_SINGLE_SIDED)

        data = filepath.read_bytes()
        assert data[:truncated_size] == bytes(buf)

    def test_expand_fills_with_zeros(self, tmp_path):
        """The extended region should be filled with zeros."""
        truncated_size = 20 * BYTES_PER_SECTOR
        expected_size = 80 * SECTORS_PER_TRACK * BYTES_PER_SECTOR
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        expand(filepath, ACORN_DFS_80T_SINGLE_SIDED)

        data = filepath.read_bytes()
        assert data[truncated_size:] == b"\x00" * (expected_size - truncated_size)

    def test_expand_full_size_returns_zero(self, tmp_path):
        """A full-size image should not be modified; returns 0 bytes added."""
        full_size = 80 * SECTORS_PER_TRACK * BYTES_PER_SECTOR
        buf = bytearray(full_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "full.ssd"
        filepath.write_bytes(buf)

        bytes_added = expand(filepath, ACORN_DFS_80T_SINGLE_SIDED)

        assert bytes_added == 0
        assert filepath.stat().st_size == full_size

    def test_expand_40t_format(self, tmp_path):
        """Expansion should respect the target format's size."""
        truncated_size = 20 * BYTES_PER_SECTOR
        expected_size = 40 * SECTORS_PER_TRACK * BYTES_PER_SECTOR  # 102400
        buf = bytearray(truncated_size)
        _minimal_catalogue(buf)

        filepath = tmp_path / "truncated.ssd"
        filepath.write_bytes(buf)

        bytes_added = expand(filepath, ACORN_DFS_40T_SINGLE_SIDED)

        assert filepath.stat().st_size == expected_size
        assert bytes_added == expected_size - truncated_size

    def test_expand_not_sector_aligned_is_padded(self, tmp_path):
        """A ragged (non-sector-multiple) file is padded up to the canonical
        size, its final partial sector absorbed and zero-filled — the
        ``disc dfs expand`` repair path for a trimmed image.
        """
        expected_size = 80 * SECTORS_PER_TRACK * BYTES_PER_SECTOR  # 204800
        filepath = tmp_path / "ragged.ssd"
        filepath.write_bytes(b"\x00" * 257)  # one sector plus one ragged byte

        bytes_added = expand(filepath, ACORN_DFS_80T_SINGLE_SIDED)

        assert filepath.stat().st_size == expected_size
        assert bytes_added == expected_size - 257

    def test_expand_oversized_raises(self, tmp_path):
        """A file larger than the canonical format size is a format error."""
        oversized = 80 * SECTORS_PER_TRACK * BYTES_PER_SECTOR + BYTES_PER_SECTOR
        filepath = tmp_path / "oversized.ssd"
        filepath.write_bytes(b"\x00" * oversized)

        with pytest.raises(InvalidFormatError, match="larger than"):
            expand(filepath, ACORN_DFS_80T_SINGLE_SIDED)

    def test_expand_empty_file_raises(self, tmp_path):
        """An empty file is a format error, reported as a domain exception."""
        filepath = tmp_path / "empty.ssd"
        filepath.write_bytes(b"")

        with pytest.raises(InvalidFormatError, match="empty"):
            expand(filepath, ACORN_DFS_80T_SINGLE_SIDED)

    def test_expand_nonexistent_raises(self, tmp_path):
        """A nonexistent file should raise FileNotFoundError."""
        filepath = tmp_path / "nonexistent.ssd"

        with pytest.raises(FileNotFoundError):
            expand(filepath, ACORN_DFS_80T_SINGLE_SIDED)


def _trimmed_to_last_byte_ssd(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    """Build an SSD trimmed to the last byte of its last file.

    Reproduces the shape of the real ``hicomal.ssd`` from the bug report
    (stardot p492650): an 80-track catalogue declaring 800 sectors, three
    files laid down contiguously, and the backing file cut off at the last
    byte of the highest-placed file — so it is neither a whole number of
    sectors nor as long as the declared disc.

    Returns the image path and a map of ``$.NAME -> content`` for the files
    written, so a reader can assert every byte survives.
    """
    contents = {
        "$.LOWROM": bytes((i * 7) & 0xFF for i in range(16384)),
        "$.HIROM": bytes((i * 11 + 3) & 0xFF for i in range(16384)),
        "$.BIGFILE": bytes((i * 13 + 5) & 0xFF for i in range(16309)),
    }

    full_filepath = tmp_path / "full.ssd"
    with DFS.create_file(full_filepath, ACORN_DFS_80T_SINGLE_SIDED, title="HICOMAL") as dfs:
        for name, data in contents.items():
            (dfs.root / name).write_bytes(data)

    # Find the highest byte any file occupies, then cut the image there —
    # exactly what a writer trimming to the last file's last byte produces.
    raw = bytearray(full_filepath.read_bytes())
    with DFS.from_file(full_filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
        last_byte = max(f.start_sector * BYTES_PER_SECTOR + f.length for f in dfs.files)

    assert last_byte % BYTES_PER_SECTOR != 0, "test fixture should be ragged"
    trimmed = raw[:last_byte]

    trimmed_filepath = tmp_path / "hicomal.ssd"
    trimmed_filepath.write_bytes(trimmed)
    return trimmed_filepath, contents


class TestTrimmedToLastByteRegression:
    """The stardot hicomal.ssd shape: declared full geometry, backing file
    trimmed to the last file's last byte (ragged, far short of declared).
    """

    def test_reads_every_file_byte_intact(self, tmp_path):
        trimmed_filepath, contents = _trimmed_to_last_byte_ssd(tmp_path)
        with DFS.from_file(trimmed_filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            for name, data in contents.items():
                assert (dfs.root / name).read_bytes() == data

    def test_validate_reports_no_defects(self, tmp_path):
        trimmed_filepath, _ = _trimmed_to_last_byte_ssd(tmp_path)
        with DFS.from_file(trimmed_filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            assert dfs.validate() == []

"""Tests for UnifiedDisc."""

import pytest

from oaknut_dfs.surface import DiscImage, SurfaceSpec
from oaknut_dfs.unified_disc import UnifiedDisc


class TestUnifiedDiscSingleSurface:
    """UnifiedDisc with a single surface should be a simple pass-through."""

    def setup_method(self):
        # 4 tracks × 4 sectors/track × 256 bytes = 4096 bytes
        self.buffer = bytearray(4096)
        # Write sector numbers into each sector's first byte
        for sector in range(16):
            self.buffer[sector * 256] = sector

        spec = SurfaceSpec(
            num_tracks=4,
            sectors_per_track=4,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=1024,
        )
        disc_image = DiscImage(memoryview(self.buffer), [spec])
        self.unified = UnifiedDisc(disc_image)

    def test_num_sectors(self):
        assert self.unified.num_sectors == 16

    def test_num_bytes(self):
        assert self.unified.num_bytes == 4096

    def test_bytes_per_sector(self):
        assert self.unified.bytes_per_sector == 256

    def test_read_single_sector(self):
        view = self.unified.sector_range(0, 1)
        assert view[0] == 0

    def test_read_multiple_sectors(self):
        view = self.unified.sector_range(0, 4)
        assert view[0] == 0
        assert view[256] == 1
        assert view[512] == 2
        assert view[768] == 3

    def test_read_last_sector(self):
        view = self.unified.sector_range(15, 1)
        assert view[0] == 15

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            self.unified.sector_range(16, 1)

    def test_negative_sector_raises(self):
        with pytest.raises(ValueError):
            self.unified.sector_range(-1, 1)

    def test_zero_count_raises(self):
        with pytest.raises(ValueError):
            self.unified.sector_range(0, 0)


class TestUnifiedDiscTwoSurfaces:
    """UnifiedDisc with two interleaved surfaces (like ADFS L)."""

    def setup_method(self):
        # 2 surfaces × 4 tracks × 4 sectors/track × 256 bytes = 8192 bytes
        # Interleaved: track 0 side 0, track 0 side 1, track 1 side 0, ...
        track_size = 4 * 256  # 1024 bytes
        self.buffer = bytearray(8192)

        # Write unified sector numbers: surface 0 gets 0-15, surface 1 gets 16-31
        for surface in range(2):
            for track in range(4):
                for sector_in_track in range(4):
                    unified_sector = surface * 16 + track * 4 + sector_in_track
                    # Physical offset: interleaved layout
                    physical_offset = (
                        track * 2 * track_size
                        + surface * track_size
                        + sector_in_track * 256
                    )
                    self.buffer[physical_offset] = unified_sector

        spec0 = SurfaceSpec(
            num_tracks=4,
            sectors_per_track=4,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2 * track_size,
        )
        spec1 = SurfaceSpec(
            num_tracks=4,
            sectors_per_track=4,
            bytes_per_sector=256,
            track_zero_offset_bytes=track_size,
            track_stride_bytes=2 * track_size,
        )
        disc_image = DiscImage(memoryview(self.buffer), [spec0, spec1])
        self.unified = UnifiedDisc(disc_image)

    def test_num_sectors(self):
        assert self.unified.num_sectors == 32

    def test_read_surface_0_sectors(self):
        """First 16 unified sectors should be surface 0."""
        for i in range(16):
            view = self.unified.sector_range(i, 1)
            assert view[0] == i, f"Unified sector {i} should contain {i}"

    def test_read_surface_1_sectors(self):
        """Unified sectors 16-31 should be surface 1."""
        for i in range(16, 32):
            view = self.unified.sector_range(i, 1)
            assert view[0] == i, f"Unified sector {i} should contain {i}"

    def test_read_across_surface_boundary(self):
        """Reading sectors that span the surface boundary."""
        view = self.unified.sector_range(14, 4)
        assert len(view) == 4 * 256
        assert view[0] == 14       # Last 2 sectors of surface 0
        assert view[256] == 15
        assert view[512] == 16     # First 2 sectors of surface 1
        assert view[768] == 17

    def test_write_through(self):
        """Writes through UnifiedDisc should propagate to the buffer."""
        view = self.unified.sector_range(20, 1)
        view[0] = 0xAA
        # Verify the buffer was modified
        view2 = self.unified.sector_range(20, 1)
        assert view2[0] == 0xAA


class TestUnifiedDiscMismatchedSectorSize:
    """UnifiedDisc should reject surfaces with different sector sizes."""

    def test_mismatched_bytes_per_sector_raises(self):
        # Use non-overlapping surfaces with different sector sizes
        buffer = bytearray(16384)
        spec0 = SurfaceSpec(
            num_tracks=2, sectors_per_track=4, bytes_per_sector=256,
            track_zero_offset_bytes=0, track_stride_bytes=1024,
        )
        spec1 = SurfaceSpec(
            num_tracks=2, sectors_per_track=2, bytes_per_sector=512,
            track_zero_offset_bytes=8192, track_stride_bytes=1024,
        )
        disc_image = DiscImage(memoryview(buffer), [spec0, spec1])
        with pytest.raises(ValueError, match="bytes_per_sector"):
            UnifiedDisc(disc_image)

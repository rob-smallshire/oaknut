"""Tests for the surface module."""
import pytest

from oaknut_dfs.surface import (
    Surface,
    SurfaceSpec,
    TrackFootprint,
    DiscImage,
    SurfaceSpecIncompatibilityError,
)


class TestSurface:
    """Tests for the Surface class.

    Surface instances are created by DiscImage, so these tests verify
    Surface properties through DiscImage construction.
    """

    def test_surface_properties(self):
        """Test Surface properties are correctly delegated to SurfaceSpec."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))  # 40 * 10 * 256
        disc = DiscImage(buffer, [spec])
        surface = disc.surface(0)

        assert surface.num_tracks == 40
        assert surface.sectors_per_track == 10
        assert surface.bytes_per_sector == 256
        assert surface.num_sectors == 400  # 40 * 10
        assert surface.num_bytes == 102400  # 40 * 10 * 256

    def test_repr(self):
        """Test __repr__ output."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        disc = DiscImage(buffer, [spec])
        surface = disc.surface(0)

        repr_str = repr(surface)
        assert "Surface" in repr_str
        assert "index=0" in repr_str
        assert "num_tracks=40" in repr_str
        assert "sectors_per_track=10" in repr_str
        assert "bytes_per_sector=256" in repr_str


class TestSurfaceSpec:
    """Tests for the SurfaceSpec class."""

    def test_valid_construction(self):
        """Test creating a valid SurfaceSpec."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        assert spec.num_tracks == 40
        assert spec.sectors_per_track == 10
        assert spec.bytes_per_sector == 256
        assert spec.track_zero_offset_bytes == 0
        assert spec.track_stride_bytes == 2560

    def test_reject_zero_tracks(self):
        """Test that zero num_tracks is rejected."""
        with pytest.raises(ValueError, match="num_tracks must be positive"):
            SurfaceSpec(
                num_tracks=0,
                sectors_per_track=10,
                bytes_per_sector=256,
                track_zero_offset_bytes=0,
                track_stride_bytes=2560,
            )

    def test_reject_negative_tracks(self):
        """Test that negative num_tracks is rejected."""
        with pytest.raises(ValueError, match="num_tracks must be positive"):
            SurfaceSpec(
                num_tracks=-1,
                sectors_per_track=10,
                bytes_per_sector=256,
                track_zero_offset_bytes=0,
                track_stride_bytes=2560,
            )

    def test_reject_zero_sectors_per_track(self):
        """Test that zero sectors_per_track is rejected."""
        with pytest.raises(ValueError, match="sectors_per_track must be positive"):
            SurfaceSpec(
                num_tracks=40,
                sectors_per_track=0,
                bytes_per_sector=256,
                track_zero_offset_bytes=0,
                track_stride_bytes=2560,
            )

    def test_reject_negative_sectors_per_track(self):
        """Test that negative sectors_per_track is rejected."""
        with pytest.raises(ValueError, match="sectors_per_track must be positive"):
            SurfaceSpec(
                num_tracks=40,
                sectors_per_track=-1,
                bytes_per_sector=256,
                track_zero_offset_bytes=0,
                track_stride_bytes=2560,
            )

    def test_reject_zero_bytes_per_sector(self):
        """Test that zero bytes_per_sector is rejected."""
        with pytest.raises(ValueError, match="bytes_per_sector must be positive"):
            SurfaceSpec(
                num_tracks=40,
                sectors_per_track=10,
                bytes_per_sector=0,
                track_zero_offset_bytes=0,
                track_stride_bytes=2560,
            )

    def test_reject_negative_bytes_per_sector(self):
        """Test that negative bytes_per_sector is rejected."""
        with pytest.raises(ValueError, match="bytes_per_sector must be positive"):
            SurfaceSpec(
                num_tracks=40,
                sectors_per_track=10,
                bytes_per_sector=-1,
                track_zero_offset_bytes=0,
                track_stride_bytes=2560,
            )

    def test_reject_stride_too_small(self):
        """Test that track_stride_bytes < minimum is rejected."""
        with pytest.raises(ValueError, match="track_stride_bytes .* is less than minimum required"):
            SurfaceSpec(
                num_tracks=40,
                sectors_per_track=10,
                bytes_per_sector=256,
                track_zero_offset_bytes=0,
                track_stride_bytes=2000,  # Too small, needs 2560
            )

    def test_reject_negative_offset(self):
        """Test that negative track_zero_offset_bytes is rejected."""
        with pytest.raises(ValueError, match="track_zero_offset_bytes must be non-negative"):
            SurfaceSpec(
                num_tracks=40,
                sectors_per_track=10,
                bytes_per_sector=256,
                track_zero_offset_bytes=-100,
                track_stride_bytes=2560,
            )

    def test_stride_can_be_larger_than_minimum(self):
        """Test that track_stride_bytes can be larger than minimum (for interleaved)."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=5120,  # Double stride for interleaved
        )
        assert spec.track_stride_bytes == 5120

    def test_is_frozen(self):
        """Test that SurfaceSpec is frozen (immutable)."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        with pytest.raises(Exception):  # FrozenInstanceError in Python 3.10+
            spec.track_zero_offset_bytes = 1000


class TestTrackFootprint:
    """Tests for the TrackFootprint class."""

    def test_overlaps_with_overlapping_ranges(self):
        """Test that overlapping ranges are detected."""
        fp1 = TrackFootprint(start=0, end=2560, surface_index=0, track_number=0)
        fp2 = TrackFootprint(start=1000, end=3560, surface_index=1, track_number=0)
        assert fp1.overlaps(fp2)
        assert fp2.overlaps(fp1)  # Symmetric

    def test_overlaps_with_non_overlapping_ranges(self):
        """Test that non-overlapping ranges are not detected as overlapping."""
        fp1 = TrackFootprint(start=0, end=2560, surface_index=0, track_number=0)
        fp2 = TrackFootprint(start=2560, end=5120, surface_index=0, track_number=1)
        assert not fp1.overlaps(fp2)
        assert not fp2.overlaps(fp1)

    def test_overlaps_with_gap_between_ranges(self):
        """Test ranges with a gap between them."""
        fp1 = TrackFootprint(start=0, end=2560, surface_index=0, track_number=0)
        fp2 = TrackFootprint(start=3000, end=5560, surface_index=0, track_number=1)
        assert not fp1.overlaps(fp2)
        assert not fp2.overlaps(fp1)

    def test_overlaps_with_fully_contained_range(self):
        """Test that a fully contained range is detected as overlapping."""
        fp1 = TrackFootprint(start=0, end=10000, surface_index=0, track_number=0)
        fp2 = TrackFootprint(start=2000, end=3000, surface_index=1, track_number=0)
        assert fp1.overlaps(fp2)
        assert fp2.overlaps(fp1)

    def test_ordering(self):
        """Test that TrackFootprints sort by start offset."""
        fp1 = TrackFootprint(start=5120, end=7680, surface_index=0, track_number=2)
        fp2 = TrackFootprint(start=0, end=2560, surface_index=0, track_number=0)
        fp3 = TrackFootprint(start=2560, end=5120, surface_index=0, track_number=1)

        footprints = [fp1, fp2, fp3]
        footprints.sort()

        assert footprints[0] == fp2  # start=0
        assert footprints[1] == fp3  # start=2560
        assert footprints[2] == fp1  # start=5120

    def test_is_frozen(self):
        """Test that TrackFootprint is frozen (immutable)."""
        fp = TrackFootprint(start=0, end=2560, surface_index=0, track_number=0)
        with pytest.raises(Exception):  # FrozenInstanceError in Python 3.10+
            fp.start = 1000


class TestDiscImage:
    """Tests for the DiscImage class."""

    def test_single_surface_ssd(self):
        """Test DiscImage with a single surface (SSD case)."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))  # 40 * 10 * 256
        disc = DiscImage(buffer, [spec])

        assert disc.num_surfaces == 1
        surface = disc.surface(0)
        assert surface.num_tracks == 40
        assert surface.sectors_per_track == 10

    def test_two_surfaces_interleaved_dsd(self):
        """Test DiscImage with two interleaved surfaces (DSD case)."""
        spec0 = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=5120,  # Interleaved
        )
        spec1 = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=2560,
            track_stride_bytes=5120,  # Interleaved
        )
        buffer = memoryview(bytearray(204800))  # 40 * 2 * 10 * 256
        disc = DiscImage(buffer, [spec0, spec1])

        assert disc.num_surfaces == 2
        assert disc.surface(0).num_tracks == 40
        assert disc.surface(1).num_tracks == 40

    def test_two_surfaces_sequential_dsd(self):
        """Test DiscImage with two sequential surfaces (DSD case)."""
        spec0 = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        spec1 = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=102400,  # After all of surface 0
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(204800))  # 40 * 2 * 10 * 256
        disc = DiscImage(buffer, [spec0, spec1])

        assert disc.num_surfaces == 2
        assert disc.surface(0).num_tracks == 40
        assert disc.surface(1).num_tracks == 40

    def test_mixed_geometry_surfaces(self):
        """Test DiscImage with surfaces of different geometries."""
        spec0 = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        spec1 = SurfaceSpec(
            num_tracks=80,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=102400,  # After surface 0
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(307200))  # 40*10*256 + 80*10*256
        disc = DiscImage(buffer, [spec0, spec1])

        assert disc.num_surfaces == 2
        assert disc.surface(0).num_tracks == 40
        assert disc.surface(1).num_tracks == 80

    def test_reject_overlapping_surfaces_complete_overlap(self):
        """Test that completely overlapping surfaces are rejected."""
        spec0 = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        spec1 = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,  # Same offset - complete overlap
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))

        with pytest.raises(SurfaceSpecIncompatibilityError, match="overlaps"):
            DiscImage(buffer, [spec0, spec1])

    def test_reject_overlapping_surfaces_partial_overlap(self):
        """Test that partially overlapping surfaces are rejected."""
        spec0 = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        spec1 = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=1000,  # Overlaps with track 0 of surface 0
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(204800))

        with pytest.raises(SurfaceSpecIncompatibilityError, match="overlaps"):
            DiscImage(buffer, [spec0, spec1])

    def test_accept_touching_but_not_overlapping_surfaces(self):
        """Test that surfaces that touch but don't overlap are accepted."""
        spec0 = SurfaceSpec(
            num_tracks=2,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        # Surface 0: track 0 at [0, 2560), track 1 at [2560, 5120)
        # Surface 1: track 0 at [5120, 7680), track 1 at [7680, 10240)
        # They touch at 5120 but don't overlap
        spec1 = SurfaceSpec(
            num_tracks=2,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=5120,  # Exactly at end of surface 0
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(10240))  # 2 * 2 * 10 * 256

        # Should not raise - they touch but don't overlap
        disc = DiscImage(buffer, [spec0, spec1])
        assert disc.num_surfaces == 2

    def test_reject_empty_surfaces_list(self):
        """Test that empty surfaces list is rejected."""
        buffer = memoryview(bytearray(1024))
        with pytest.raises(ValueError, match="At least one surface must be specified"):
            DiscImage(buffer, [])

    def test_surface_index_out_of_bounds(self):
        """Test that out-of-bounds surface index raises IndexError."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        disc = DiscImage(buffer, [spec])

        with pytest.raises(IndexError, match="surface_index out of range"):
            disc.surface(1)

        with pytest.raises(IndexError, match="surface_index out of range"):
            disc.surface(-1)

    def test_buffer_too_small(self):
        """Test that buffer size validation rejects buffers that are too small."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(50000))  # Too small for 40 tracks

        with pytest.raises(ValueError, match="requires .* bytes but buffer is only"):
            DiscImage(buffer, [spec])

    def test_buffer_exactly_right_size(self):
        """Test that buffer size validation accepts buffers of exactly the right size."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))  # Exactly 40 * 10 * 256
        disc = DiscImage(buffer, [spec])
        assert disc.num_surfaces == 1

    def test_buffer_larger_than_needed(self):
        """Test that buffer size validation accepts buffers larger than needed."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(200000))  # Larger than needed
        disc = DiscImage(buffer, [spec])
        assert disc.num_surfaces == 1

    def test_repr(self):
        """Test __repr__ output."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        disc = DiscImage(buffer, [spec])

        repr_str = repr(disc)
        assert "DiscImage" in repr_str

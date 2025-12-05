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


class TestSurfaceSectors:
    """Tests for Surface.sectors() method."""

    def test_sectors_single(self):
        """Test getting a single sector."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        buffer[1280:1536] = b"X" * 256  # Sector 5

        disc = DiscImage(buffer, [spec])
        surface = disc.surface(0)

        sectors_view = surface.sector_range(5, 1)
        assert len(sectors_view) == 256
        assert bytes(sectors_view) == b"X" * 256

    def test_sectors_multiple(self):
        """Test getting multiple sectors."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        buffer[1280:2048] = b"ABC" * 256  # Sectors 5-7

        disc = DiscImage(buffer, [spec])
        surface = disc.surface(0)

        sectors_view = surface.sector_range(5, 3)
        assert len(sectors_view) == 768  # 3 * 256
        assert bytes(sectors_view[:3]) == b"ABC"

    def test_sectors_across_track_boundary(self):
        """Test getting sectors that span track boundaries."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        # Sectors 9-11 cross track 0→1 boundary
        buffer[2304:2560] = b"A" * 256  # Sector 9
        buffer[2560:2816] = b"B" * 256  # Sector 10
        buffer[2816:3072] = b"C" * 256  # Sector 11

        disc = DiscImage(buffer, [spec])
        surface = disc.surface(0)

        sectors_view = surface.sector_range(9, 3)
        assert len(sectors_view) == 768
        data = bytes(sectors_view)
        assert data[:256] == b"A" * 256
        assert data[256:512] == b"B" * 256
        assert data[512:768] == b"C" * 256

    def test_sectors_interleaved_layout(self):
        """Test with interleaved DSD layout (larger stride)."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=5120,  # Skips other side
        )
        buffer = memoryview(bytearray(204800))
        buffer[0:256] = b"0" * 256       # Sector 0 (track 0)
        buffer[5120:5376] = b"1" * 256   # Sector 10 (track 1)

        disc = DiscImage(buffer, [spec])
        surface = disc.surface(0)

        # Get sectors 0 and 10
        view0 = surface.sector_range(0, 1)
        assert bytes(view0) == b"0" * 256

        view10 = surface.sector_range(10, 1)
        assert bytes(view10) == b"1" * 256

    def test_sectors_writes_through(self):
        """Test that writes to Sectors update the buffer."""
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

        sectors_view = surface.sector_range(5, 2)
        sectors_view[0:5] = b"Hello"

        # Verify buffer was updated
        assert bytes(buffer[1280:1285]) == b"Hello"

    def test_sectors_validation(self):
        """Test validation of sector range."""
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

        # Negative start
        with pytest.raises(ValueError, match="must be non-negative"):
            surface.sector_range(-1, 5)

        # Zero/negative count
        with pytest.raises(ValueError, match="must be positive"):
            surface.sector_range(0, 0)

        with pytest.raises(ValueError, match="must be positive"):
            surface.sector_range(0, -1)

        # Out of bounds
        with pytest.raises(ValueError, match="exceeds surface bounds"):
            surface.sector_range(395, 10)  # Would need sectors 395-404, but only 0-399 exist


class TestDiscImageGetSectorViews:
    """Tests for DiscImage.get_sector_views() method."""

    def test_get_sector_views_single_sector(self):
        """Test getting a single sector returns one memoryview."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        buffer[1280:1536] = b"X" * 256  # Sector 5

        disc = DiscImage(buffer, [spec])

        # Get sector 5 directly from DiscImage
        views = disc.sector_views(0, [5])
        assert len(views) == 1
        assert len(views[0]) == 256
        assert bytes(views[0]) == b"X" * 256

    def test_get_sector_views_merges_contiguous_sectors(self):
        """Test that physically contiguous sectors are merged into one memoryview."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        buffer[1280:2048] = b"ABCDEFGH" * 96  # Sectors 5-7 (3 contiguous sectors)

        disc = DiscImage(buffer, [spec])

        # Request sectors 5, 6, 7 - should return ONE memoryview
        views = disc.sector_views(0, [5, 6, 7])
        assert len(views) == 1
        assert len(views[0]) == 768  # 3 * 256
        assert bytes(views[0][:8]) == b"ABCDEFGH"

    def test_get_sector_views_preserves_non_contiguous_sectors(self):
        """Test that non-contiguous sectors are kept separate."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        buffer[1280:1536] = b"A" * 256  # Sector 5
        buffer[2048:2304] = b"B" * 256  # Sector 8 (gap at sectors 6-7)

        disc = DiscImage(buffer, [spec])

        # Request sectors 5, 8 - should return TWO memoryviews
        views = disc.sector_views(0, [5, 8])
        assert len(views) == 2
        assert len(views[0]) == 256
        assert len(views[1]) == 256
        assert bytes(views[0]) == b"A" * 256
        assert bytes(views[1]) == b"B" * 256

    def test_get_sector_views_across_track_boundary(self):
        """Test merging works across track boundaries."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        # Sectors 9-11 span track 0->1 boundary but are contiguous
        buffer[2304:3072] = b"XYZ" * 256

        disc = DiscImage(buffer, [spec])

        # Request sectors 9, 10, 11 - should merge into ONE memoryview
        views = disc.sector_views(0, [9, 10, 11])
        assert len(views) == 1
        assert len(views[0]) == 768  # 3 * 256

    def test_get_sector_views_interleaved_dsd_no_merge(self):
        """Test that interleaved DSD sectors don't merge (they're not contiguous)."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=5120,  # Interleaved - skips other side
        )
        buffer = memoryview(bytearray(204800))
        buffer[0:256] = b"A" * 256       # Sector 0 (track 0)
        buffer[256:512] = b"B" * 256     # Sector 1 (track 0)
        buffer[5120:5376] = b"C" * 256   # Sector 10 (track 1)

        disc = DiscImage(buffer, [spec])

        # Sectors 0-1 are contiguous, but 10 is far away
        views = disc.sector_views(0, [0, 1, 10])
        assert len(views) == 2  # [0-1], [10]
        assert len(views[0]) == 512  # Sectors 0-1 merged
        assert len(views[1]) == 256  # Sector 10 alone

    def test_get_sector_views_unsorted_input(self):
        """Test that method handles unsorted sector numbers correctly."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        buffer[1280:2048] = b"X" * 768  # Sectors 5-7

        disc = DiscImage(buffer, [spec])

        # Request in reverse order - should still merge
        views = disc.sector_views(0, [7, 6, 5])
        assert len(views) == 1
        assert len(views[0]) == 768

    def test_get_sector_views_empty_list(self):
        """Test that empty sector list returns empty views list."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        disc = DiscImage(buffer, [spec])

        views = disc.sector_views(0, [])
        assert views == []

    def test_get_sector_views_validation(self):
        """Test validation in get_sector_views."""
        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        buffer = memoryview(bytearray(102400))
        disc = DiscImage(buffer, [spec])

        # Invalid surface index
        with pytest.raises(IndexError):
            disc.sector_views(1, [0])  # Only surface 0 exists

        # Invalid sector number
        with pytest.raises(ValueError):
            disc.sector_views(0, [400])  # Only 0-399 exist

        # Mix of valid and invalid
        with pytest.raises(ValueError):
            disc.sector_views(0, [5, 400])

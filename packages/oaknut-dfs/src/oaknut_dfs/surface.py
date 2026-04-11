from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

from typename import typename

from oaknut_dfs.sectors_view import SectorsView as Sectors


class Surface:
    """A single disc surface.

    A single-sided disc has one surface. A double-sided disc has two surfaces.
    Surface instances are created by DiscImage and reference their parent DiscImage.
    """

    def __init__(self, disc_image: DiscImage, spec: SurfaceSpec, index: int):
        self._disc_image = disc_image
        self._spec = spec
        self._index = index

    def __repr__(self):
        return (
            f"{typename(self)}(index={self._index}, "
            f"num_tracks={self._spec.num_tracks}, "
            f"sectors_per_track={self._spec.sectors_per_track}, "
            f"bytes_per_sector={self._spec.bytes_per_sector})"
        )

    @property
    def num_tracks(self) -> int:
        return self._spec.num_tracks

    @property
    def sectors_per_track(self) -> int:
        return self._spec.sectors_per_track

    @property
    def bytes_per_sector(self) -> int:
        return self._spec.bytes_per_sector

    @property
    def num_sectors(self) -> int:
        return self._spec.num_tracks * self._spec.sectors_per_track

    @property
    def num_bytes(self) -> int:
        return self.num_sectors * self._spec.bytes_per_sector

    def sector_range(self, start_sector: int, num_sectors: int) -> Sectors:
        """
        Create a Sectors view for a range of sectors.

        Args:
            start_sector: First sector number (0-based)
            num_sectors: Number of sectors to include

        Returns:
            Sectors view wrapping the sector range

        Raises:
            ValueError: If range is invalid or out of bounds
        """
        # Validation
        if start_sector < 0:
            raise ValueError(f"start_sector must be non-negative, got {start_sector}")
        if num_sectors <= 0:
            raise ValueError(f"num_sectors must be positive, got {num_sectors}")
        if start_sector + num_sectors > self.num_sectors:
            raise ValueError(
                f"Sector range [{start_sector}, {start_sector + num_sectors}) "
                f"exceeds surface bounds (0-{self.num_sectors})"
            )

        # Delegate to DiscImage for physical sector access (optimized to merge contiguous sectors)
        sector_numbers = list(range(start_sector, start_sector + num_sectors))
        views = self._disc_image.sector_views(self._index, sector_numbers)

        return Sectors(views)


@dataclass(frozen=True)
class SurfaceSpec:
    """Specification of how a surface maps to a disc image."""
    num_tracks: int
    sectors_per_track: int
    bytes_per_sector: int
    track_zero_offset_bytes: int  # Offset in bytes within the disc image where this surface starts
    track_stride_bytes: int  # Number of bytes from the start of one track to the start of the next track

    def __post_init__(self):
        if self.num_tracks <= 0:
            raise ValueError("num_tracks must be positive")
        if self.sectors_per_track <= 0:
            raise ValueError("sectors_per_track must be positive")
        if self.bytes_per_sector <= 0:
            raise ValueError("bytes_per_sector must be positive")
        if self.track_zero_offset_bytes < 0:
            raise ValueError("track_zero_offset_bytes must be non-negative")

        minimum_stride = self.sectors_per_track * self.bytes_per_sector
        if self.track_stride_bytes < minimum_stride:
            raise ValueError(
                f"track_stride_bytes {self.track_stride_bytes} is less than minimum required {minimum_stride}"
            )


@dataclass(frozen=True, order=True)
class TrackFootprint:
    """The byte range a track occupies in a disc image."""
    start: int          # Byte offset where track starts (compared first)
    end: int            # Byte offset where track ends (exclusive)
    surface_index: int  # Which surface this track belongs to
    track_number: int   # Track number within that surface

    def overlaps(self, other: "TrackFootprint") -> bool:
        """Check if this footprint overlaps with another footprint."""
        return self.start < other.end and other.start < self.end


class SurfaceSpecIncompatibilityError(Exception):
    """Raised when two surface specifications are incompatible (i.e. overlap in the disc image)."""
    pass


class DiscImage:
    """A disc image with one or more surfaces."""

    def __init__(
        self,
        buffer: memoryview,
        surface_specs: Iterable[SurfaceSpec],
    ):
        self._buffer = buffer
        surface_specs = list(surface_specs)
        if len(surface_specs) == 0:
            raise ValueError("At least one surface must be specified")

        self._surface_specs = self._valid_disjoint_surfaces(surface_specs)
        self._validate_buffer_size(surface_specs, len(buffer))
        self._surfaces = [Surface(self, spec, i) for i, spec in enumerate(surface_specs)]

    @property
    def buffer(self) -> memoryview:
        """The underlying buffer containing the disc image data."""
        return self._buffer

    @staticmethod
    def _validate_buffer_size(surface_specs: list[SurfaceSpec], buffer_size: int) -> None:
        """Check that all surface specs fit within the buffer size."""
        for i, spec in enumerate(surface_specs):
            # Calculate the maximum offset needed for this surface
            bytes_per_track = spec.sectors_per_track * spec.bytes_per_sector
            max_offset = (
                spec.track_zero_offset_bytes
                + (spec.num_tracks - 1) * spec.track_stride_bytes
                + bytes_per_track
            )
            if max_offset > buffer_size:
                raise ValueError(
                    f"Surface {i} requires {max_offset} bytes but buffer is only {buffer_size} bytes"
                )

    @staticmethod
    def _valid_disjoint_surfaces(surface_specs: list[SurfaceSpec]) -> list[SurfaceSpec]:
        """Check that no two surfaces overlap in the disc image."""

        # Collect all track footprints
        footprints = []
        for surface_idx, spec in enumerate(surface_specs):
            bytes_per_track = spec.sectors_per_track * spec.bytes_per_sector

            for track_num in range(spec.num_tracks):
                start = spec.track_zero_offset_bytes + track_num * spec.track_stride_bytes
                end = start + bytes_per_track
                footprints.append(TrackFootprint(start, end, surface_idx, track_num))

        # Sort by start offset
        footprints.sort()

        # Check consecutive footprints don't overlap
        for a, b in pairwise(footprints):
            if a.overlaps(b):
                raise SurfaceSpecIncompatibilityError(
                    f"Surface {a.surface_index} track {a.track_number} overlaps with "
                    f"surface {b.surface_index} track {b.track_number}"
                )
        return surface_specs

    def __repr__(self):
        return f"{typename(self)}(surfaces_specs={self._surface_specs})"

    @property
    def num_surfaces(self) -> int:
        return len(self._surface_specs)

    def surface(self, surface_index: int) -> Surface:
        """Get the Surface object for the given surface index."""
        if not 0 <= surface_index < self.num_surfaces:
            raise IndexError("surface_index out of range")
        return self._surfaces[surface_index]

    def sector_views(self, surface_index: int, sector_numbers: list[int]) -> list[memoryview]:
        """
        Get memoryviews for sectors on a surface, optimized to merge contiguous sectors.

        This method encapsulates all knowledge of physical sector layout. When multiple
        sectors are physically adjacent in the buffer, they are merged into a single
        memoryview for efficiency.

        Args:
            surface_index: Which surface (0-based)
            sector_numbers: List of logical sector numbers within that surface (0-based)

        Returns:
            List of memoryview slices (may be fewer than len(sector_numbers) if sectors
            are physically contiguous)

        Raises:
            IndexError: If surface_index is out of range
            ValueError: If any sector_number is out of range for that surface
        """
        if not 0 <= surface_index < self.num_surfaces:
            raise IndexError(f"surface_index {surface_index} out of range")

        if not sector_numbers:
            return []

        spec = self._surface_specs[surface_index]
        max_sectors = spec.num_tracks * spec.sectors_per_track

        # Calculate physical offset ranges for each sector
        ranges = []
        for sector_number in sector_numbers:
            if not 0 <= sector_number < max_sectors:
                raise ValueError(
                    f"sector_number {sector_number} out of range for surface {surface_index} "
                    f"(max {max_sectors})"
                )

            track_number = sector_number // spec.sectors_per_track
            sector_in_track = sector_number % spec.sectors_per_track

            start_offset = (
                spec.track_zero_offset_bytes
                + track_number * spec.track_stride_bytes
                + sector_in_track * spec.bytes_per_sector
            )
            end_offset = start_offset + spec.bytes_per_sector

            ranges.append((start_offset, end_offset))

        # Sort by start offset
        ranges.sort()

        # Merge contiguous ranges
        merged_ranges = []
        current_start, current_end = ranges[0]

        for start, end in ranges[1:]:
            if start == current_end:
                # Adjacent - extend current range
                current_end = end
            else:
                # Gap - save current range and start new one
                merged_ranges.append((current_start, current_end))
                current_start, current_end = start, end

        # Don't forget the last range
        merged_ranges.append((current_start, current_end))

        # Create memoryviews for merged ranges
        return [self._buffer[start:end] for start, end in merged_ranges]
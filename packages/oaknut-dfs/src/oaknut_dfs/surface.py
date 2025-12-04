from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

from typename import typename


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
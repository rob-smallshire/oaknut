"""Generic disk-format machinery shared by oaknut filesystem packages.

Defines the ``DiskFormat`` dataclass and helpers for constructing
``SurfaceSpec`` lists for common disc-image layouts (single-sided,
interleaved double-sided, sequential double-sided). Filesystem
packages compose these into concrete format constants — e.g.
``oaknut.dfs.formats.ACORN_DFS_40T_SINGLE_SIDED`` — and ship them
alongside the filesystem they describe.
"""

from dataclasses import dataclass

from oaknut.discimage.surface import SurfaceSpec

BYTES_PER_SECTOR = 256


@dataclass(frozen=True)
class DiskFormat:
    """Complete disk format specification including all surfaces and catalogue type."""

    surface_specs: list[SurfaceSpec]
    catalogue_name: str

    def __post_init__(self):
        if not self.surface_specs:
            raise ValueError("At least one surface_spec is required")


def single_sided_spec(
    num_tracks: int, sectors_per_track: int, bytes_per_sector: int = BYTES_PER_SECTOR
) -> SurfaceSpec:
    """Create SurfaceSpec for a single-sided disc image."""
    track_size_bytes = sectors_per_track * bytes_per_sector
    return SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=sectors_per_track,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=0,
        track_stride_bytes=track_size_bytes,
    )


def interleaved_double_sided_specs(
    num_tracks: int, sectors_per_track: int, bytes_per_sector: int = BYTES_PER_SECTOR
) -> list[SurfaceSpec]:
    """Create SurfaceSpecs for an interleaved double-sided disc image.

    The physical layout alternates sides per track (side 0 track 0,
    side 1 track 0, side 0 track 1, …).
    """
    track_size_bytes = sectors_per_track * bytes_per_sector
    spec0 = SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=sectors_per_track,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=0,
        track_stride_bytes=2 * track_size_bytes,
    )
    spec1 = SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=sectors_per_track,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=track_size_bytes,
        track_stride_bytes=2 * track_size_bytes,
    )
    return [spec0, spec1]


def sequential_double_sided_specs(
    num_tracks: int, sectors_per_track: int, bytes_per_sector: int = BYTES_PER_SECTOR
) -> list[SurfaceSpec]:
    """Create SurfaceSpecs for a sequential double-sided disc image.

    The physical layout is all of side 0 first, then all of side 1.
    """
    track_size_bytes = sectors_per_track * bytes_per_sector
    side_size_bytes = num_tracks * track_size_bytes
    spec0 = SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=sectors_per_track,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=0,
        track_stride_bytes=track_size_bytes,
    )
    spec1 = SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=sectors_per_track,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=side_size_bytes,
        track_stride_bytes=track_size_bytes,
    )
    return [spec0, spec1]


__all__ = [
    "BYTES_PER_SECTOR",
    "DiskFormat",
    "single_sided_spec",
    "interleaved_double_sided_specs",
    "sequential_double_sided_specs",
]

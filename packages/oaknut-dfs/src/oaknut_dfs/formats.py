"""Disk format definitions for various DFS variants."""

from dataclasses import dataclass

from oaknut_dfs.surface import SurfaceSpec

# Base constants (shared across formats)
BYTES_PER_SECTOR = 256
ACORN_DFS_SECTORS_PER_TRACK = 10
ACORN_DFS_CATALOGUE_NAME = "acorn-dfs"
WATFORD_DFS_CATALOGUE_NAME = "watford-dfs"

# Track counts
TRACKS_40 = 40
TRACKS_80 = 80


@dataclass(frozen=True)
class DiskFormat:
    """Complete disk format specification including all surfaces and catalogue type."""

    surface_specs: list[SurfaceSpec]
    catalogue_name: str

    def __post_init__(self):
        if not self.surface_specs:
            raise ValueError("At least one surface_spec is required")


# Helper functions for building SurfaceSpecs


def _single_sided_spec(
    num_tracks: int, sectors_per_track: int, bytes_per_sector: int
) -> SurfaceSpec:
    """Create SurfaceSpec for single-sided disk."""
    track_size_bytes = sectors_per_track * bytes_per_sector
    return SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=sectors_per_track,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=0,
        track_stride_bytes=track_size_bytes,
    )


def _interleaved_double_sided_specs(
    num_tracks: int, sectors_per_track: int, bytes_per_sector: int
) -> list[SurfaceSpec]:
    """Create SurfaceSpecs for interleaved double-sided disk (alternating sides by track)."""
    track_size_bytes = sectors_per_track * bytes_per_sector

    # Side 0: tracks 0, 2, 4, ... (starts at offset 0)
    spec0 = SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=sectors_per_track,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=0,
        track_stride_bytes=2 * track_size_bytes,  # Skip every other track
    )

    # Side 1: tracks 1, 3, 5, ... (starts at offset track_size_bytes)
    spec1 = SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=sectors_per_track,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=track_size_bytes,
        track_stride_bytes=2 * track_size_bytes,  # Skip every other track
    )

    return [spec0, spec1]


def _sequential_double_sided_specs(
    num_tracks: int, sectors_per_track: int, bytes_per_sector: int
) -> list[SurfaceSpec]:
    """Create SurfaceSpecs for sequential double-sided disk (all side 0, then all side 1)."""
    track_size_bytes = sectors_per_track * bytes_per_sector
    side_size_bytes = num_tracks * track_size_bytes

    # Side 0: tracks 0-39 contiguous
    spec0 = SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=sectors_per_track,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=0,
        track_stride_bytes=track_size_bytes,
    )

    # Side 1: tracks 40-79 contiguous (starts after all side 0 tracks)
    spec1 = SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=sectors_per_track,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=side_size_bytes,
        track_stride_bytes=track_size_bytes,
    )

    return [spec0, spec1]


# Predefined format constants (6 total: 2 single-sided + 4 double-sided)

# 40-track formats
ACORN_DFS_40T_SINGLE_SIDED = DiskFormat(
    surface_specs=[
        _single_sided_spec(TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR)
    ],
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED = DiskFormat(
    surface_specs=_interleaved_double_sided_specs(
        TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL = DiskFormat(
    surface_specs=_sequential_double_sided_specs(
        TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

# 80-track formats
ACORN_DFS_80T_SINGLE_SIDED = DiskFormat(
    surface_specs=[
        _single_sided_spec(TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR)
    ],
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED = DiskFormat(
    surface_specs=_interleaved_double_sided_specs(
        TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL = DiskFormat(
    surface_specs=_sequential_double_sided_specs(
        TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

# Watford DFS formats (62-file catalog, same geometry as Acorn DFS: 10 sectors/track)

# 40-track formats
WATFORD_DFS_40T_SINGLE_SIDED = DiskFormat(
    surface_specs=[
        _single_sided_spec(TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR)
    ],
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_40T_DOUBLE_SIDED_INTERLEAVED = DiskFormat(
    surface_specs=_interleaved_double_sided_specs(
        TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_40T_DOUBLE_SIDED_SEQUENTIAL = DiskFormat(
    surface_specs=_sequential_double_sided_specs(
        TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

# 80-track formats
WATFORD_DFS_80T_SINGLE_SIDED = DiskFormat(
    surface_specs=[
        _single_sided_spec(TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR)
    ],
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_80T_DOUBLE_SIDED_INTERLEAVED = DiskFormat(
    surface_specs=_interleaved_double_sided_specs(
        TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_80T_DOUBLE_SIDED_SEQUENTIAL = DiskFormat(
    surface_specs=_sequential_double_sided_specs(
        TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

# Export all format constants
__all__ = [
    "DiskFormat",
    "ACORN_DFS_40T_SINGLE_SIDED",
    "ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED",
    "ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL",
    "ACORN_DFS_80T_SINGLE_SIDED",
    "ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED",
    "ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL",
    "WATFORD_DFS_40T_SINGLE_SIDED",
    "WATFORD_DFS_40T_DOUBLE_SIDED_INTERLEAVED",
    "WATFORD_DFS_40T_DOUBLE_SIDED_SEQUENTIAL",
    "WATFORD_DFS_80T_SINGLE_SIDED",
    "WATFORD_DFS_80T_DOUBLE_SIDED_INTERLEAVED",
    "WATFORD_DFS_80T_DOUBLE_SIDED_SEQUENTIAL",
]

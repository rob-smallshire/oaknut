"""DFS and Watford DFS disc format constants.

The generic ``DiscFormat`` dataclass and ``SurfaceSpec`` helpers
live in ``oaknut.discimage.formats``; this module defines the concrete
Acorn-DFS and Watford-DFS format instances built on top of them.
"""

from oaknut.discimage.formats import (
    BYTES_PER_SECTOR,
    DiscFormat,
    interleaved_double_sided_specs,
    sequential_double_sided_specs,
    single_sided_spec,
)

ACORN_DFS_SECTORS_PER_TRACK = 10
ACORN_DFS_CATALOGUE_NAME = "acorn-dfs"
WATFORD_DFS_CATALOGUE_NAME = "watford-dfs"

TRACKS_40 = 40
TRACKS_80 = 80


ACORN_DFS_40T_SINGLE_SIDED = DiscFormat(
    surface_specs=[single_sided_spec(TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR)],
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED = DiscFormat(
    surface_specs=interleaved_double_sided_specs(
        TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL = DiscFormat(
    surface_specs=sequential_double_sided_specs(
        TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

ACORN_DFS_80T_SINGLE_SIDED = DiscFormat(
    surface_specs=[single_sided_spec(TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR)],
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED = DiscFormat(
    surface_specs=interleaved_double_sided_specs(
        TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL = DiscFormat(
    surface_specs=sequential_double_sided_specs(
        TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=ACORN_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_40T_SINGLE_SIDED = DiscFormat(
    surface_specs=[single_sided_spec(TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR)],
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_40T_DOUBLE_SIDED_INTERLEAVED = DiscFormat(
    surface_specs=interleaved_double_sided_specs(
        TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_40T_DOUBLE_SIDED_SEQUENTIAL = DiscFormat(
    surface_specs=sequential_double_sided_specs(
        TRACKS_40, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_80T_SINGLE_SIDED = DiscFormat(
    surface_specs=[single_sided_spec(TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR)],
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_80T_DOUBLE_SIDED_INTERLEAVED = DiscFormat(
    surface_specs=interleaved_double_sided_specs(
        TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)

WATFORD_DFS_80T_DOUBLE_SIDED_SEQUENTIAL = DiscFormat(
    surface_specs=sequential_double_sided_specs(
        TRACKS_80, ACORN_DFS_SECTORS_PER_TRACK, BYTES_PER_SECTOR
    ),
    catalogue_name=WATFORD_DFS_CATALOGUE_NAME,
)


__all__ = [
    "ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED",
    "ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL",
    "ACORN_DFS_40T_SINGLE_SIDED",
    "ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED",
    "ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL",
    "ACORN_DFS_80T_SINGLE_SIDED",
    "ACORN_DFS_CATALOGUE_NAME",
    "ACORN_DFS_SECTORS_PER_TRACK",
    "DiscFormat",
    "WATFORD_DFS_40T_DOUBLE_SIDED_INTERLEAVED",
    "WATFORD_DFS_40T_DOUBLE_SIDED_SEQUENTIAL",
    "WATFORD_DFS_40T_SINGLE_SIDED",
    "WATFORD_DFS_80T_DOUBLE_SIDED_INTERLEAVED",
    "WATFORD_DFS_80T_DOUBLE_SIDED_SEQUENTIAL",
    "WATFORD_DFS_80T_SINGLE_SIDED",
    "WATFORD_DFS_CATALOGUE_NAME",
]

"""Disc-image sector abstractions for Acorn filesystem packages.

This package hosts the sector-level building blocks shared by every
Acorn filesystem that is backed by a physical disc image: the
``Surface`` abstraction, the ``SectorsView`` buffer wrapper,
``UnifiedDisc`` for ADFS-style linearised sector access, and the
generic ``DiscFormat`` dataclass. Filesystem-specific constants
(e.g. ACORN_DFS_* geometries) live alongside the filesystem itself
in its own package, not here.
"""

__version__ = "12.0.0"

from oaknut.discimage.formats import (
    BYTES_PER_SECTOR,
    DiscFormat,
    interleaved_double_sided_specs,
    sequential_double_sided_specs,
    single_sided_spec,
)
from oaknut.discimage.open_image import open_image_mmap
from oaknut.discimage.sectors_view import SectorsView
from oaknut.discimage.surface import DiscImage, Surface, SurfaceSpec
from oaknut.discimage.unified_disc import UnifiedDisc

__all__ = [
    "BYTES_PER_SECTOR",
    "DiscFormat",
    "DiscImage",
    "SectorsView",
    "Surface",
    "SurfaceSpec",
    "UnifiedDisc",
    "interleaved_double_sided_specs",
    "open_image_mmap",
    "sequential_double_sided_specs",
    "single_sided_spec",
]

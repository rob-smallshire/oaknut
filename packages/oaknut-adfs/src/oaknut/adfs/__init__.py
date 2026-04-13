"""Acorn ADFS disc image support.

Handles the ADFS (Acorn Advanced Disc Filing System) formats used
by the BBC Master, Acorn Archimedes, and RISC OS machines: small (S),
medium (M), and large (L) floppy layouts plus hard-disc images.
"""

__version__ = "10.0.5"

from oaknut.adfs.adfs import (
    ADFS,
    ADFS_L,
    ADFS_M,
    ADFS_S,
    ADFSFormat,
    ADFSGeometry,
    ADFSPath,
    ADFSStat,
    geometry_for_capacity,
)
from oaknut.adfs.directory import Access

__all__ = [
    "ADFS",
    "ADFS_L",
    "ADFS_M",
    "ADFS_S",
    "ADFSFormat",
    "ADFSGeometry",
    "ADFSPath",
    "ADFSStat",
    "Access",
    "geometry_for_capacity",
]

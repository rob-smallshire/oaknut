"""Acorn ADFS disc image support.

Handles the ADFS (Acorn Advanced Disc Filing System) formats used
by the BBC Master, Acorn Archimedes, and RISC OS machines: small (S),
medium (M), and large (L) floppy layouts plus hard-disc images.
"""

__version__ = "12.13.1"

from oaknut.adfs.adfs import (
    ADFS,
    ADFS_D,
    ADFS_E,
    ADFS_E_PLUS,
    ADFS_F,
    ADFS_F_PLUS,
    ADFS_G,
    ADFS_G_PLUS,
    ADFS_L,
    ADFS_M,
    ADFS_S,
    IMAGE_FORMAT_BY_EXTENSION,
    ADFSFormat,
    ADFSGeometry,
    ADFSPath,
    ADFSStat,
    geometry_for_capacity,
    write_dsc,
)

__all__ = [
    "ADFS",
    "ADFS_D",
    "ADFS_E",
    "ADFS_E_PLUS",
    "ADFS_F",
    "ADFS_F_PLUS",
    "ADFS_G",
    "ADFS_G_PLUS",
    "ADFS_L",
    "ADFS_M",
    "ADFS_S",
    "IMAGE_FORMAT_BY_EXTENSION",
    "ADFSFormat",
    "ADFSGeometry",
    "ADFSPath",
    "ADFSStat",
    "geometry_for_capacity",
    "write_dsc",
]

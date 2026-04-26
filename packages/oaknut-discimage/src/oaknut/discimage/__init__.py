"""Disc-image sector abstractions for Acorn filesystem packages.

This package hosts the sector-level building blocks shared by every
Acorn filesystem that is backed by a physical disc image: the
``Surface`` abstraction, the ``SectorsView`` buffer wrapper,
``UnifiedDisc`` for ADFS-style linearised sector access, and the
generic ``DiskFormat`` dataclass. Filesystem-specific constants
(e.g. ACORN_DFS_* geometries) live alongside the filesystem itself
in its own package, not here.
"""

__version__ = "10.6.0"

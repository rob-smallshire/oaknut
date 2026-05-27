"""The pluggable filesystem contract for the oaknut family.

A *filesystem* (Acorn DFS, Watford DDFS, ADFS, AFS, …) is the unit of
extension, registered on the ``oaknut.filesystem`` entry-point axis. Each
:class:`Filesystem` detects itself (:meth:`Filesystem.probe`), opens a
region into a :class:`Mount` exposing a small core plus opt-in capability
protocols, and declares its physical :class:`Geometry` grammar.

Geometry (the physical byte→sector layout) and the filesystem (the
logical structure) are kept strictly apart. :func:`identify` runs the
registered filesystems over an image, ranks the candidates, and recurses
into reserved regions to build a per-partition :class:`Identification`
tree — depending on, and importing, no concrete filesystem package.
"""

from oaknut.filesystem.capabilities import (
    AcornMetadata,
    Bootable,
    DirectoryTitled,
    Entry,
    FreeSpace,
    HierarchicalDirectories,
    Mount,
    RegionHost,
    Titled,
    UserDatabase,
)
from oaknut.filesystem.coordinator import (
    create_filesystem,
    describe_filesystem,
    filesystem_names,
    identify,
)
from oaknut.filesystem.exceptions import (
    FilesystemError,
    FilesystemExtensionError,
    GeometryError,
)
from oaknut.filesystem.filesystem import (
    FILESYSTEM_KIND,
    FILESYSTEM_NAMESPACE,
    Filesystem,
)
from oaknut.filesystem.geometry import (
    FLOPPY,
    WINCHESTER,
    Geometry,
    GeometryGrammar,
    floppy_geometry,
    region_reader,
    winchester_geometry,
)
from oaknut.filesystem.identification import Confidence, Identification, Partition
from oaknut.filesystem.reader import ImageReader, ImageSource, reader_for

__version__ = "11.2.0"

__all__ = [
    # contract
    "Filesystem",
    "FILESYSTEM_KIND",
    "FILESYSTEM_NAMESPACE",
    # capabilities
    "Mount",
    "Entry",
    "HierarchicalDirectories",
    "AcornMetadata",
    "Titled",
    "DirectoryTitled",
    "Bootable",
    "FreeSpace",
    "UserDatabase",
    "RegionHost",
    # geometry
    "Geometry",
    "GeometryGrammar",
    "floppy_geometry",
    "winchester_geometry",
    "region_reader",
    "FLOPPY",
    "WINCHESTER",
    # identification
    "Confidence",
    "Identification",
    "Partition",
    # coordinator
    "identify",
    "filesystem_names",
    "describe_filesystem",
    "create_filesystem",
    # reader
    "ImageReader",
    "ImageSource",
    "reader_for",
    # exceptions
    "FilesystemError",
    "GeometryError",
    "FilesystemExtensionError",
]

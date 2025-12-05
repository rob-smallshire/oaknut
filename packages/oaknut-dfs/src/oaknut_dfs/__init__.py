from collections import namedtuple

from oaknut_dfs.dfs_filesystem import (
    DFSImage,
    BootOption,
    FileInfo,
    DiskInfo,
    FORMAT_SSD,
    FORMAT_DSD_INTERLEAVED,
    FORMAT_DSD_SEQUENTIAL,
)

Version = namedtuple("Version", ["major", "minor", "patch"])

__version__ = "0.1.0"
__version_info__ = Version(*(__version__.split(".")))

__all__ = [
    "DFSImage",
    "BootOption",
    "FileInfo",
    "DiskInfo",
    "FORMAT_SSD",
    "FORMAT_DSD_INTERLEAVED",
    "FORMAT_DSD_SEQUENTIAL",
]

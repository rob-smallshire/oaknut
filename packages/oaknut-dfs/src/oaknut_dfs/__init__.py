from collections import namedtuple

# Import acorn_encoding to register the codec
import oaknut_dfs.acorn_encoding  # noqa: F401

# Import catalogue implementations to register them
import oaknut_dfs.acorn_dfs_catalogue  # noqa: F401
import oaknut_dfs.watford_dfs_catalogue  # noqa: F401

from oaknut_dfs.adfs import ADFS, ADFS_L, ADFS_M, ADFS_S, ADFSFormat, ADFSPath, ADFSStat
from oaknut_dfs.boot_option import BootOption
from oaknut_dfs.catalogue import DiskInfo, FileInfo
from oaknut_dfs.dfs import DFS, DFSPath, DFSStat
from oaknut_dfs.formats import (
    ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL,
    ACORN_DFS_40T_SINGLE_SIDED,
    ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL,
    ACORN_DFS_80T_SINGLE_SIDED,
    DiskFormat,
)

Version = namedtuple("Version", ["major", "minor", "patch"])

__version__ = "0.1.3"
__version_info__ = Version(*(__version__.split(".")))

__all__ = [
    "ADFS",
    "ADFS_S",
    "ADFS_M",
    "ADFS_L",
    "ADFSFormat",
    "ADFSPath",
    "ADFSStat",
    "DFS",
    "DFSPath",
    "DFSStat",
    "DiskFormat",
    "ACORN_DFS_40T_SINGLE_SIDED",
    "ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED",
    "ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL",
    "ACORN_DFS_80T_SINGLE_SIDED",
    "ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED",
    "ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL",
    "BootOption",
    "FileInfo",
    "DiskInfo",
]

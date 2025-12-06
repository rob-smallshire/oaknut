from collections import namedtuple

# Import acorn_encoding to register the codec
import oaknut_dfs.acorn_encoding  # noqa: F401

from oaknut_dfs.boot_option import BootOption
from oaknut_dfs.catalogue import DiskInfo, FileInfo
from oaknut_dfs.dfs import DFS
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

__version__ = "0.1.0"
__version_info__ = Version(*(__version__.split(".")))

__all__ = [
    "DFS",
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

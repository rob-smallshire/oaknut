from collections import namedtuple

# Import catalogue implementations to register them
import oaknut.dfs.acorn_dfs_catalogue  # noqa: F401
import oaknut.dfs.watford_dfs_catalogue  # noqa: F401

# Import acorn_encoding to register the codec
import oaknut.file.acorn_encoding  # noqa: F401
from oaknut.dfs.catalogue import DiscInfo
from oaknut.dfs.dfs import DFS, DFSPath, DFSStat, detect_dfs_format, expand
from oaknut.dfs.formats import (
    ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL,
    ACORN_DFS_40T_SINGLE_SIDED,
    ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL,
    ACORN_DFS_80T_SINGLE_SIDED,
    IMAGE_FORMAT_BY_EXTENSION,
)

Version = namedtuple("Version", ["major", "minor", "patch"])

__version__ = "12.5.2"
__version_info__ = Version(*(__version__.split(".")))

__all__ = [
    "DFS",
    "DFSPath",
    "DFSStat",
    "DiscInfo",
    "ACORN_DFS_40T_SINGLE_SIDED",
    "ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED",
    "ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL",
    "ACORN_DFS_80T_SINGLE_SIDED",
    "ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED",
    "ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL",
    "IMAGE_FORMAT_BY_EXTENSION",
    "detect_dfs_format",
    "expand",
]

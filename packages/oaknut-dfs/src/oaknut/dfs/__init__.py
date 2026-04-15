from collections import namedtuple

# Import catalogue implementations to register them
import oaknut.dfs.acorn_dfs_catalogue  # noqa: F401
import oaknut.dfs.watford_dfs_catalogue  # noqa: F401

# Import acorn_encoding to register the codec
import oaknut.file.acorn_encoding  # noqa: F401
from oaknut.dfs.catalogue import DiskInfo
from oaknut.dfs.dfs import DFS, DFSPath, DFSStat, expand
from oaknut.dfs.formats import (
    ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_40T_DOUBLE_SIDED_SEQUENTIAL,
    ACORN_DFS_40T_SINGLE_SIDED,
    ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_80T_DOUBLE_SIDED_SEQUENTIAL,
    ACORN_DFS_80T_SINGLE_SIDED,
    DiskFormat,
)
from oaknut.file import (
    SOURCE_DIR,
    SOURCE_FILENAME,
    SOURCE_INF_PIEB,
    SOURCE_INF_TRAD,
    SOURCE_SPARKFS,
    AcornMeta,
    MetaFormat,
)
from oaknut.file.boot_option import BootOption
from oaknut.file.exceptions import FSError
from oaknut.file.host_bridge import (
    DEFAULT_EXPORT_META_FORMAT,
    DEFAULT_IMPORT_META_FORMATS,
    SOURCE_XATTR_ACORN,
    SOURCE_XATTR_PIEB,
    export_with_metadata,
    import_with_metadata,
)

Version = namedtuple("Version", ["major", "minor", "patch"])

__version__ = "10.2.0"
__version_info__ = Version(*(__version__.split(".")))

__all__ = [
    "AcornMeta",
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
    "DiskInfo",
    "FSError",
    "MetaFormat",
    "SOURCE_DIR",
    "SOURCE_FILENAME",
    "SOURCE_INF_PIEB",
    "SOURCE_INF_TRAD",
    "SOURCE_SPARKFS",
    "SOURCE_XATTR_ACORN",
    "SOURCE_XATTR_PIEB",
    "DEFAULT_EXPORT_META_FORMAT",
    "DEFAULT_IMPORT_META_FORMATS",
    "expand",
    "export_with_metadata",
    "import_with_metadata",
]

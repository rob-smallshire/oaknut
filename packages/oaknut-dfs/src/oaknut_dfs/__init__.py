from collections import namedtuple

# Import acorn_encoding to register the codec
import oaknut_dfs.acorn_encoding  # noqa: F401

# Import catalogue implementations to register them
import oaknut_dfs.acorn_dfs_catalogue  # noqa: F401
import oaknut_dfs.watford_dfs_catalogue  # noqa: F401

from oaknut_file import (
    AcornMeta,
    MetaFormat,
    SOURCE_DIR,
    SOURCE_FILENAME,
    SOURCE_INF_PIEB,
    SOURCE_INF_TRAD,
    SOURCE_SPARKFS,
)

from oaknut_dfs.adfs import (
    ADFS,
    ADFS_L,
    ADFS_M,
    ADFS_S,
    ADFSFormat,
    ADFSPath,
    ADFSStat,
    geometry_for_capacity,
)
from oaknut_dfs.adfs_directory import Access
from oaknut_dfs.boot_option import BootOption
from oaknut_dfs.exceptions import FSError
from oaknut_dfs.catalogue import DiskInfo
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
from oaknut_dfs.host_bridge import (
    DEFAULT_EXPORT_META_FORMAT,
    DEFAULT_IMPORT_META_FORMATS,
    SOURCE_XATTR_ACORN,
    SOURCE_XATTR_PIEB,
    export_with_metadata,
    import_with_metadata,
)

Version = namedtuple("Version", ["major", "minor", "patch"])

__version__ = "3.0.0"
__version_info__ = Version(*(__version__.split(".")))

__all__ = [
    "Access",
    "AcornMeta",
    "ADFS",
    "ADFS_S",
    "ADFS_M",
    "ADFS_L",
    "ADFSFormat",
    "ADFSPath",
    "ADFSStat",
    "geometry_for_capacity",
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
    "export_with_metadata",
    "import_with_metadata",
]

from collections import namedtuple

from oaknut_dfs.boot_option import BootOption
from oaknut_dfs.catalogue import DiskInfo, FileInfo
from oaknut_dfs.dfs import DFS

Version = namedtuple("Version", ["major", "minor", "patch"])

__version__ = "0.1.0"
__version_info__ = Version(*(__version__.split(".")))

__all__ = [
    "DFS",
    "BootOption",
    "FileInfo",
    "DiskInfo",
]

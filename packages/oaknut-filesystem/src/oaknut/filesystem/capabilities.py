"""The mounted-filesystem interface: a small core plus opt-in capabilities.

Every mounted filesystem provides the :class:`Mount` core. Beyond that,
features differ wildly — a flat DFS catalogue, a hierarchical ADFS tree,
AFS user accounts, a foreign FAT with none of Acorn's metadata — so the
extras are **opt-in capability protocols** the CLI feature-detects with
``isinstance`` (each is ``runtime_checkable``). A command is "available
when the mount provides capability X", never "when the filesystem is Y".

These signatures establish the *shape* of the contract; they will be
refined as the concrete filesystems are wrapped (Phase B).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from oaknut.file import AcornMeta, BootOption
    from oaknut.filesystem.identification import Partition


@dataclass(frozen=True)
class Entry:
    """One directory entry, in filesystem-agnostic terms.

    Acorn-specific metadata (load/exec/access) is reached through the
    :class:`AcornMetadata` capability, not carried here, so a foreign
    filesystem's entries need none of it.
    """

    name: str
    is_dir: bool
    length: int = 0


@runtime_checkable
class Mount(Protocol):
    """The core every mounted filesystem provides.

    Paths are strings in the *filesystem's own* syntax (`$.DIR.FILE` for
    Acorn, `\\DIR\\FILE` for FAT, `D.DIR.FILE` for a DDOS volume); the
    filesystem parses them — the CLI never does.
    """

    def path_root(self) -> str:
        """The root path string (e.g. ``"$"`` for Acorn filesystems)."""
        ...

    def iter_entries(self, path: str) -> Iterable[Entry]:
        """Yield the entries of the directory at *path*."""
        ...

    def exists(self, path: str) -> bool:
        """Whether anything exists at *path*."""
        ...

    def read_bytes(self, path: str) -> bytes:
        """The contents of the file at *path*."""
        ...

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write *data* to *path*, creating or replacing the file."""
        ...


@runtime_checkable
class HierarchicalDirectories(Protocol):
    """The filesystem nests directories arbitrarily (ADFS, AFS, FAT, DDOS).

    Its absence marks a flat catalogue (Acorn/Watford DFS: a single
    top-level directory only).
    """

    def make_directory(self, path: str) -> None:
        """Create a directory at *path*."""
        ...


@runtime_checkable
class AcornMetadata(Protocol):
    """Files carry Acorn load/exec addresses and an access byte."""

    def acorn_meta(self, path: str) -> "AcornMeta":
        """The Acorn metadata of the file at *path*."""
        ...

    def set_acorn_meta(self, path: str, meta: "AcornMeta") -> None:
        """Replace the Acorn metadata of the file at *path*."""
        ...


@runtime_checkable
class DiscMetadata(Protocol):
    """The disc carries a title and a boot option."""

    @property
    def title(self) -> str:
        """The disc title / name."""
        ...

    @property
    def boot_option(self) -> "BootOption":
        """The disc's *OPT 4 boot option."""
        ...


@runtime_checkable
class UserDatabase(Protocol):
    """The filesystem has user accounts (AFS passwords / quota)."""

    def user_names(self) -> tuple[str, ...]:
        """The names of the registered users."""
        ...


@runtime_checkable
class RegionHost(Protocol):
    """The filesystem reserves regions another filesystem may occupy.

    An ADFS host reserves tail cylinders that an AFS or (DRDOS) FAT
    filesystem lives in; the coordinator recurses into these. The host
    stays ignorant of *what* occupies them.
    """

    def reserved_regions(self) -> tuple["Partition", ...]:
        """The regions reserved within this filesystem, for recursion."""
        ...

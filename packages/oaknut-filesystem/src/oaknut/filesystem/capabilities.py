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
    #: The entry's full in-partition path, so a caller can address it
    #: (e.g. fetch its metadata) without re-joining in the filesystem's
    #: own syntax. Empty only for a bare, unaddressed entry.
    path: str = ""


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

    def stat(self, path: str) -> Entry:
        """The :class:`Entry` for *path* (name, kind, length, full path)."""
        ...

    def join(self, parent: str, name: str) -> str:
        """The path of child *name* under directory *parent*.

        The filesystem owns its path syntax (``$.A`` for Acorn, the root
        sometimes nameless), so the CLI builds new paths through this
        rather than concatenating — needed when creating a path that does
        not exist yet (e.g. a bulk import target).
        """
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

    def remove(self, path: str, *, force: bool = False) -> None:
        """Delete the file or directory at *path*.

        A directory is removed if the filesystem represents one (a flat
        catalogue has none, so removing its notional directory is a
        no-op). *force* overrides a lock — the filesystem unlocks the
        entry first, owning its own locked-entry semantics so the access
        byte's layout never leaks to the caller.
        """
        ...

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename / move the entry at *old_path* to *new_path* in place."""
        ...


@runtime_checkable
class HierarchicalDirectories(Protocol):
    """The filesystem nests directories arbitrarily (ADFS, AFS, FAT, DDOS).

    Its absence marks a flat catalogue (Acorn/Watford DFS: a single
    top-level directory only).
    """

    def make_directory(
        self,
        path: str,
        *,
        parents: bool = False,
        exist_ok: bool = False,
        title: str | None = None,
    ) -> None:
        """Create a directory at *path*.

        *parents* creates missing ancestors; *exist_ok* tolerates an
        existing directory. *title* sets the new directory's title where
        the filesystem supports per-directory titles (ADFS) and is
        rejected (before anything is created) where it does not (AFS).
        """
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
class Titled(Protocol):
    """The disc carries a title / name (DFS, ADFS, AFS)."""

    @property
    def title(self) -> str:
        """The disc title / name."""
        ...


@runtime_checkable
class Bootable(Protocol):
    """The disc carries a ``*OPT 4`` boot option (DFS, ADFS)."""

    @property
    def boot_option(self) -> "BootOption":
        """The disc's ``*OPT 4`` boot option."""
        ...


@runtime_checkable
class FreeSpace(Protocol):
    """The filesystem reports its free space (ADFS, AFS)."""

    def free_bytes(self) -> int:
        """Free space remaining, in bytes."""
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

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
    from _typeshed import SupportsRichComparison
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

    def set_title(self, title: str) -> None:
        """Set the disc title / name."""
        ...


@runtime_checkable
class DirectoryTitled(Protocol):
    """Directories carry their own title, distinct from the disc's (ADFS).

    Its absence marks a filesystem whose directories have no title field
    (DFS, AFS) — setting one there is rejected.
    """

    def directory_title(self, path: str) -> str:
        """The title of the directory at *path*."""
        ...

    def set_directory_title(self, path: str, title: str) -> None:
        """Set the title of the directory at *path*."""
        ...


@runtime_checkable
class Bootable(Protocol):
    """The disc carries a ``*OPT 4`` boot option (DFS, ADFS)."""

    @property
    def boot_option(self) -> "BootOption":
        """The disc's ``*OPT 4`` boot option."""
        ...

    def set_boot_option(self, option: "BootOption | int") -> None:
        """Set the disc's ``*OPT 4`` boot option."""
        ...


@runtime_checkable
class FreeSpace(Protocol):
    """The filesystem reports its free space (ADFS, AFS)."""

    def free_bytes(self) -> int:
        """Free space remaining, in bytes."""
        ...


@runtime_checkable
class Sized(Protocol):
    """The filesystem reports its own occupied size (its partition's span)."""

    def size_bytes(self) -> int:
        """The size of this filesystem's partition, in bytes.

        For a filesystem sharing a disc (ADFS with an AFS tail) this is
        its slice, not the whole image — so partition sizes sum to the
        disc.
        """
        ...


@dataclass(frozen=True)
class DiscGeometry:
    """A disc's physical geometry, for the ``stat`` summary.

    *label* is a human description in the filesystem's own vocabulary
    (ADFS speaks cylinders/heads/track; AFS speaks cylinders/sectors-per-
    cylinder). *sectors_per_cylinder* lets the caller place a partition's
    logical-sector span into a cylinder range without parsing the label.
    """

    label: str
    sectors_per_cylinder: int
    total_sectors: int


@runtime_checkable
class PhysicalGeometry(Protocol):
    """The filesystem knows the disc's physical geometry (ADFS, AFS).

    A flat-catalogue floppy filesystem (DFS) records no geometry and does
    not advertise this.
    """

    def disc_geometry(self) -> DiscGeometry:
        """The disc's physical geometry."""
        ...


@dataclass(frozen=True)
class FreeMapData:
    """A filesystem's free space as partition-relative sector runs.

    Carries no geometry: the renderer lays the *total_sectors* out as a
    sector matrix sized to the terminal, marking those in *free_regions*
    free and the rest used. Each region is ``(start_sector, length)``.
    """

    free_regions: tuple[tuple[int, int], ...]
    total_sectors: int


@runtime_checkable
class FreeMap(Protocol):
    """The filesystem can report which of its sectors are free."""

    def free_map(self) -> FreeMapData:
        """The free-space map as partition-relative sector runs."""
        ...


@runtime_checkable
class Compactable(Protocol):
    """The filesystem can defragment in place, consolidating free space."""

    def compact(self) -> int:
        """Defragment, returning a filesystem-defined measure of work done."""
        ...


@runtime_checkable
class Validatable(Protocol):
    """The filesystem can check its on-disc structure for defects."""

    def validate(self) -> list:
        """Return a list of structural defects (empty when clean).

        The entries are the filesystem's own validation-error objects,
        rendered by the CLI's error formatter; the caller treats them
        opaquely.
        """
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


@runtime_checkable
class StatusReporting(Protocol):
    """The filesystem can report human-readable status notes for ``stat``.

    Notes are short advisories about the partition as a whole — for example
    that a ROMFS image is an incomplete fragment of a multi-ROM set, or is
    read-only because it carries code after the filing system. ``disc stat``
    renders them as a line; most filesystems have nothing to say and do not
    implement this.
    """

    def status_notes(self) -> tuple[str, ...]:
        """Short status advisories for this partition (empty when none)."""
        ...


@runtime_checkable
class StorageOrdered(Protocol):
    """The filesystem can order its paths by physical position on the medium.

    :meth:`storage_key` returns an opaque sort key for a path; sorting a
    directory's siblings by it yields the order in which their data is laid
    down on the medium — ascending start sector for a random-access
    filesystem (DFS, ADFS), stream order for a sequential one (CFS/ROMFS).
    A multi-file ``cp`` uses it to reproduce the source's on-disc order at
    the destination instead of reversing it (a flat catalogue read
    highest-sector-first, re-laid lowest-sector-first, would otherwise
    flip the order and slow loading on a seeking drive).

    The key is comparable only against other keys from the *same* mount and
    carries no meaning beyond ordering — the caller never inspects it.
    Filesystems with no storage order (a hash table) or one that is
    ill-defined (a fragmented AFS file spans many extents, so it has no
    single position) do not implement this.
    """

    def storage_key(self, path: str) -> "SupportsRichComparison":
        """An opaque, sortable key for *path*'s position on the medium."""
        ...

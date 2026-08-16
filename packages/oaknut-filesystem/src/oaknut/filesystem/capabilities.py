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

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime, timedelta

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
class Filetyped(Protocol):
    """Files carry a RISC OS filetype.

    On ADFS the filetype is folded into the load address (the ``0xFFF``
    marker); a filesystem with nowhere to keep one simply does not
    provide this capability.
    """

    def filetype(self, path: str) -> int | None:
        """The 12-bit filetype of the file at *path*, or None if untyped."""
        ...

    def set_filetype(self, path: str, filetype: int) -> None:
        """Set the filetype of the file at *path*."""
        ...


@runtime_checkable
class Datestamped(Protocol):
    """Files carry a single datestamp.

    The instant is naive local time. Filesystems differ in resolution —
    ADFS keeps centiseconds in its load/exec fields, AFS only a calendar
    day — so :attr:`datestamp_resolution` reports the granularity and a
    caller renders the value to suit (a bare date when the resolution is
    a day or coarser).
    """

    @property
    def datestamp_resolution(self) -> "timedelta":
        """The smallest datestamp increment this filesystem records."""
        ...

    def datestamp(self, path: str) -> "datetime | None":
        """The datestamp of the file at *path*, or None if unstamped."""
        ...

    def set_datestamp(self, path: str, when: "datetime") -> None:
        """Set the datestamp of the file at *path* (naive local time)."""
        ...


class Lens(enum.Enum):
    """How a mount's load/exec fields should be read by default.

    On practically every Acorn filesystem the 32-bit load and exec
    addresses can double as a RISC OS filetype and datestamp (the
    ``0xFFF`` marker in the top of the load address). Which reading a
    user *wants* is format-dependent, and the ``0xFFF`` marker overlaps
    genuine addresses (``&FFFF0E00`` and friends), so the choice cannot
    be made per file from the bytes alone. A mount declares its
    preference and the CLI honours it unless overridden.
    """

    #: Present the raw load and execution addresses. The default for
    #: DFS and the 8-bit ADFS shapes (S/M/L, Old directories).
    ADDRESSES = "addresses"
    #: Decode a filetype and datestamp from the load/exec pair. The
    #: default for the Arthur/RISC OS ADFS shapes (D and the New/Big
    #: directory formats).
    TYPE_DATE = "type-date"


@runtime_checkable
class MetadataLensed(Protocol):
    """A mount that declares a default :class:`Lens` for its metadata.

    Feature-detected by the CLI to resolve ``--metadata=auto``; a mount
    that does not provide it is read as :attr:`Lens.ADDRESSES`. The lens
    is presentational only — it selects which reading of the load/exec
    fields is shown, never what is stored. Filesystems that keep a
    datestamp *independently* of load/exec (AFS, with its native
    ``AfsDate``) need not implement it: their datestamp shows under
    either lens.
    """

    @property
    def metadata_lens(self) -> Lens:
        """The reading of load/exec this mount prefers by default."""
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

    def compact(self, *, order: Sequence[str] = ()) -> int:
        """Defragment, returning a filesystem-defined measure of work done.

        *order* is a partial list of paths to lay down first, in the
        lowest/earliest positions (in the given order); files it does not
        name follow in their current order. It lets a caller place boot or
        loader files where they load fastest. A filesystem whose layout
        order is fixed or undefined rejects a non-empty *order*; the CLI
        offers ``--order`` only where the mount also reports a storage
        order (:class:`StorageOrdered`).
        """
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


@dataclass(frozen=True)
class WildcardSyntax:
    """A filesystem's filename-wildcard vocabulary, for help and errors.

    Each pair is ``(metacharacter, what it matches)`` — Acorn filing
    systems use ``*`` and ``#``; a DOS/FAT filesystem uses ``*`` and
    ``?``. This carries only the human-facing description; the matching
    itself is :meth:`WildcardMatching.matches`, since a syntax like DOS
    8.3 is more than a choice of metacharacters.
    """

    metacharacters: tuple[tuple[str, str], ...]

    @property
    def chars(self) -> str:
        """Just the metacharacters, e.g. ``"*#"`` — for detecting a pattern."""
        return "".join(char for char, _meaning in self.metacharacters)

    def summary(self) -> str:
        """A one-line gloss, e.g. ``"* (any sequence), # (one character)"``."""
        return ", ".join(f"{char} ({meaning})" for char, meaning in self.metacharacters)


@runtime_checkable
class WildcardMatching(Protocol):
    """The filesystem owns its filename wildcard syntax and matching.

    Acorn filing systems glob with ``*`` and ``#``, and ``?`` is an
    ordinary filename character; a DOS/FAT filesystem globs with ``*`` and
    ``?``. The CLI defers to the mount so a pattern is read in the
    filesystem's own terms, falling back to a Unix default (``*`` / ``?``)
    for a mount that does not implement this.
    """

    @property
    def wildcard_syntax(self) -> WildcardSyntax:
        """This filesystem's wildcard vocabulary, for help and diagnostics."""
        ...

    def is_pattern(self, name: str) -> bool:
        """Whether *name* contains any wildcard metacharacter of this syntax."""
        ...

    def matches(self, pattern: str, name: str) -> bool:
        """Whether *name* matches the wildcard *pattern* under this syntax."""
        ...


@dataclass(frozen=True)
class NameGrammar:
    """The rules a leaf filename must satisfy to be *stored* on a filesystem.

    Both enforcing and self-describing: :meth:`validate` raises on a name
    the on-disc name field cannot hold, and :meth:`summary` renders the
    same rules for ``disc describe-filesystem``. A filesystem advertises
    its grammar through :attr:`Filesystem.name_grammar`.

    Deliberately *liberal*: it constrains only what the format genuinely
    cannot represent, never what the command line finds awkward. Wildcard
    metacharacters are therefore valid name bytes unless a filesystem
    truly cannot store them — selecting such a name literally versus as a
    pattern is the matching layer's concern (see :class:`WildcardMatching`
    and the ``--no-wildcards`` option), not storage's. Reading is always
    liberal: a name already on the medium is never refused.

    The fields cover the Acorn filing systems' single fixed-width name
    field. A filesystem whose names are not one bounded field (DOS 8.3,
    say) supplies its own object with the same ``validate``/``summary``
    surface rather than reusing this.
    """

    #: Maximum number of characters in a name.
    max_length: int
    #: Characters that may not appear anywhere in a name.
    forbidden: str = ""
    #: Human gloss naming *why* :attr:`forbidden` are excluded, e.g.
    #: ``"the drive (:) and directory (.) separators"``.
    forbidden_reason: str = ""
    #: Reject bytes with the top bit set (the seven-bit name field).
    seven_bit: bool = True
    #: Permit control characters (< 0x20). Almost never true.
    allow_control: bool = False
    #: How case is handled: ``"fold-upper"`` (stored upper-cased),
    #: ``"insensitive"`` (stored as written, matched case-insensitively),
    #: or ``"sensitive"`` (case distinguishes names).
    case: str = "fold-upper"
    #: Text codec a name must round-trip through, or ``None``. Looked up
    #: by name at validation time, so this module need not import it.
    codec: str | None = None
    #: Extra human-facing lines for :meth:`summary` — anything notable a
    #: reader should know (which metacharacters are storable, and so on).
    notes: tuple[str, ...] = ()

    def name_key(self, name: str) -> str:
        """The canonical key for comparing two names for *equality*.

        Two names denote the same object on this filesystem iff their keys
        are equal — so this is the one comparator a filesystem's lookup,
        duplicate-detection and collation should route through rather than
        hard-coding a fold. Case is folded for the case-insensitive
        policies (``fold-upper`` / ``insensitive``) and preserved for
        ``sensitive``.
        """
        if self.case in ("fold-upper", "insensitive"):
            return name.upper()
        return name

    def validate(self, name: str) -> None:
        """Raise :class:`ValueError` if *name* cannot be stored.

        Liberal: enforces only length, the :attr:`forbidden` set, the
        seven-bit / control-character bounds, and codec round-tripping.
        """
        if not name:
            raise ValueError("Filename cannot be empty")
        if len(name) > self.max_length:
            raise ValueError(f"Filename too long: '{name}' (max {self.max_length} chars)")
        for char in name:
            if char in self.forbidden:
                raise ValueError(f"Forbidden character '{char}' in filename '{name}'")
            code_point = ord(char)
            if self.seven_bit and code_point > 127:
                raise ValueError(
                    f"Character '{char}' (code {code_point}) has top bit set in '{name}'"
                )
            if not self.allow_control and code_point < 32:
                raise ValueError(f"Control character (code {code_point}) not allowed in '{name}'")
        if self.codec is not None:
            try:
                name.encode(self.codec)
            except (UnicodeEncodeError, LookupError) as exc:
                raise ValueError(f"Filename contains invalid characters: {exc}")

    def summary(self) -> str:
        """A multi-line description of the rules, for ``describe-filesystem``."""
        lines = [f"Length: up to {self.max_length} characters."]
        if self.forbidden:
            shown = " ".join(_render_forbidden(char) for char in self.forbidden)
            reason = f" ({self.forbidden_reason})" if self.forbidden_reason else ""
            lines.append(f"Forbidden: {shown}{reason}.")
        else:
            lines.append("Forbidden: none beyond the byte-range limits below.")
        case = {
            "fold-upper": "folded to upper case",
            "insensitive": "preserved as written, matched case-insensitively",
            "sensitive": "case-sensitive",
        }.get(self.case, "case-preserving")
        lines.append(f"Case: {case}.")
        width = "seven-bit" if self.seven_bit else "eight-bit"
        top = "0x7F" if self.seven_bit else "0xFF"
        if self.allow_control:
            lines.append(f"Bytes: {width} (0x00–{top}), control characters allowed.")
        else:
            top = "0x7E" if self.seven_bit else "0xFF"
            lines.append(f"Bytes: {width} (0x20–{top}), no control characters.")
        lines.extend(self.notes)
        return "\n".join(lines)


#: Readable names for forbidden characters that would otherwise be
#: invisible or confusing in a ``describe-filesystem`` listing.
_FORBIDDEN_CHAR_NAMES = {" ": "space", "\r": "CR", "\n": "LF", "\t": "TAB", "\x7f": "DEL"}


def _render_forbidden(char: str) -> str:
    """A printable token for *char* in a forbidden-character listing."""
    if char in _FORBIDDEN_CHAR_NAMES:
        return _FORBIDDEN_CHAR_NAMES[char]
    if ord(char) < 0x20:
        return f"&{ord(char):02X}"
    return char

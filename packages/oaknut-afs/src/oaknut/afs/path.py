"""AFSPath — pathlib-inspired navigation of AFS directories.

``AFSPath`` is a value type representing an absolute path within an
AFS region. It mirrors the shape of ``ADFSPath`` in ``oaknut.adfs``:
immutable, composable via ``/``, and the primary public surface for
locating files and directories.

Paths always begin at ``$`` (the root directory). Parts are joined
with ``.`` (dot) — the AFS name separator per ``Uade02:119``. Name
parts are up to 10 characters each (``NAMLNT``).

An :class:`AFSPath` optionally holds a reference to the :class:`AFS`
handle it was obtained from. The bound form (returned by ``afs.root``
and by ``/``) can perform read operations (:meth:`read_bytes`,
:meth:`stat`, directory iteration). Unbound paths, constructed via
``AFSPath.root()`` or ``AFSPath.parse()``, are pure values useful
for path arithmetic and tests, and raise :class:`AFSPathError` if
asked to perform I/O.

The ``afs`` reference is a non-comparing field: two paths are equal
iff their ``parts`` match regardless of which (or no) AFS they came
from. This keeps path algebra clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator, Union

from oaknut.afs.directory import MAX_NAME_LENGTH
from oaknut.afs.exceptions import AFSPathError

if TYPE_CHECKING:
    from oaknut.afs.afs import AFS
    from oaknut.afs.directory import DirectoryEntry

ROOT = "$"
SEPARATOR = "."


def _validate_part(part: str) -> None:
    """Validate a single path component.

    The rules come from ``Uade02`` and Beebmaster's PDF:

    - non-empty
    - ≤ 10 characters
    - must not contain the separator ``.`` or the disc-introducer
      ``:`` or a space (space is used as a pad character on disc)
    """
    if not part:
        raise AFSPathError("path component must not be empty")
    if part == ROOT:
        return  # the root marker is always valid
    if len(part) > MAX_NAME_LENGTH:
        raise AFSPathError(f"path component {part!r} exceeds {MAX_NAME_LENGTH} characters")
    for ch in part:
        if ch in (SEPARATOR, ":", " "):
            raise AFSPathError(f"path component {part!r} contains forbidden character {ch!r}")


@dataclass(frozen=True, slots=True)
class AFSPath:
    """An absolute path within an AFS directory tree.

    Paths always start at the root ``$`` and accumulate named
    components through ``/``::

        root = AFSPath.root()
        library = root / "Library"
        fs_tool = library / "Fs"
        str(fs_tool)  # "$.Library.Fs"

    ``AFSPath`` values are immutable; ``/`` returns a new path.
    """

    parts: tuple[str, ...]
    afs: "AFS | None" = field(default=None, compare=False, repr=False, hash=False)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        for part in self.parts:
            _validate_part(part)

    @classmethod
    def root(cls) -> AFSPath:
        return cls((ROOT,))

    @classmethod
    def _bound_root(cls, afs: "AFS") -> AFSPath:
        """Construct a root path bound to an :class:`AFS` handle."""
        return cls((ROOT,), afs=afs)

    @classmethod
    def parse(cls, text: str) -> AFSPath:
        """Parse a dot-separated path string into an :class:`AFSPath`.

        The string must start at the root ``$``; relative paths are
        not supported for this phase.
        """
        if not text:
            raise AFSPathError("empty path")
        if text == ROOT:
            return cls.root()
        if not text.startswith(ROOT + SEPARATOR):
            raise AFSPathError(f"path {text!r} must start at root {ROOT!r}")
        # Skip the leading "$."
        rest = text[len(ROOT) + 1 :]
        parts: list[str] = [ROOT]
        if rest:
            parts.extend(rest.split(SEPARATOR))
        return cls(tuple(parts))

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def __truediv__(self, other: Union[str, "AFSPath"]) -> AFSPath:
        if isinstance(other, AFSPath):
            if other.is_absolute():
                raise AFSPathError(f"cannot append absolute path {other} to {self}")
            return AFSPath(self.parts + other.parts, afs=self.afs)
        if not isinstance(other, str):
            return NotImplemented
        _validate_part(other)
        return AFSPath(self.parts + (other,), afs=self.afs)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """The final component of the path."""
        return self.parts[-1]

    @property
    def parent(self) -> AFSPath:
        """The path with the final component removed.

        The parent of the root is the root itself.
        """
        if len(self.parts) <= 1:
            return self
        return AFSPath(self.parts[:-1], afs=self.afs)

    def is_root(self) -> bool:
        return self.parts == (ROOT,)

    def is_absolute(self) -> bool:
        return len(self.parts) > 0 and self.parts[0] == ROOT

    def __str__(self) -> str:
        if self.is_root():
            return ROOT
        return SEPARATOR.join(self.parts)

    def __repr__(self) -> str:
        return f"AFSPath({str(self)!r})"

    def __fspath__(self) -> str:
        return str(self)

    # ------------------------------------------------------------------
    # Bound I/O — requires an AFS handle
    # ------------------------------------------------------------------

    def _require_afs(self) -> "AFS":
        if self.afs is None:
            raise AFSPathError(
                f"path {self} is not bound to an AFS handle; "
                "obtain paths via afs.root to read from disc"
            )
        return self.afs

    def exists(self) -> bool:
        """Check whether this path resolves to an object on disc."""
        afs = self._require_afs()
        try:
            afs._resolve(self)
        except AFSPathError:
            return False
        return True

    def is_dir(self) -> bool:
        """True if this path is a directory."""
        afs = self._require_afs()
        if self.is_root():
            return True
        _, entry = afs._resolve(self)
        return entry.is_directory

    def is_file(self) -> bool:
        """True if this path is a file (not a directory)."""
        afs = self._require_afs()
        if self.is_root():
            return False
        _, entry = afs._resolve(self)
        return not entry.is_directory

    def read_bytes(self) -> bytes:
        """Return the full contents of this file as bytes.

        Raises :class:`AFSPathError` if the path is the root or a
        directory rather than a file.
        """
        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot read_bytes on the root directory")
        _, entry = afs._resolve(self)
        if entry.is_directory:
            raise AFSPathError(f"{self} is a directory, not a file")
        return afs._read_object_bytes(entry.sin)

    def stat(self) -> "DirectoryEntry":
        """Return the directory entry for this path.

        The root directory has no parent entry and is a special case;
        asking for its ``stat`` raises :class:`AFSPathError`.
        """
        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot stat the root directory")
        _, entry = afs._resolve(self)
        return entry

    def iterdir(self) -> Iterator[AFSPath]:
        """Yield the children of this directory as bound ``AFSPath``s.

        Raises :class:`AFSPathError` if this path is a file.
        """
        afs = self._require_afs()
        directory = afs._resolve_directory(self)
        for child_entry in directory:
            yield self / child_entry.name

    def __iter__(self) -> Iterator[AFSPath]:
        return self.iterdir()

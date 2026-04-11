"""AFSPath — pathlib-inspired navigation of AFS directories.

``AFSPath`` is a value type representing an absolute path within an
AFS region. It mirrors the shape of ``ADFSPath`` in ``oaknut.adfs``:
immutable, composable via ``/``, and the primary public surface for
locating files and directories.

Paths always begin at ``$`` (the root directory). Parts are joined
with ``.`` (dot) — the AFS name separator per ``Uade02:119``. Name
parts are up to 10 characters each (``NAMLNT``).

Phase 5 covers construction and navigation. The actual read
operations (``read_bytes``, ``stat``, iteration of directories)
will wire through an ``AFS`` handle in phase 6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from oaknut.afs.directory import MAX_NAME_LENGTH
from oaknut.afs.exceptions import AFSPathError

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
            return AFSPath(self.parts + other.parts)
        if not isinstance(other, str):
            return NotImplemented
        _validate_part(other)
        return AFSPath(self.parts + (other,))

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
        return AFSPath(self.parts[:-1])

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

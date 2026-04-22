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
    from oaknut.afs.access import AFSAccess
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
    def path(self) -> str:
        """The canonical dot-separated path string (``$.A.B``).

        Symmetrical with :attr:`DFSPath.path` and
        :attr:`ADFSPath.path` so tooling that walks heterogeneous
        trees can call ``.path`` without type-discriminating.
        """
        return str(self)

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

    # ------------------------------------------------------------------
    # Write path — phases 11-13
    # ------------------------------------------------------------------

    def write_bytes(
        self,
        data: bytes,
        *,
        load_address: int = 0,
        exec_address: int = 0,
        access=None,
        date=None,
    ) -> None:
        """Create or replace a file at this path with ``data``.

        If an object already exists at this path it is freed first,
        its directory entry is rewritten, and the new content is
        placed in freshly-allocated sectors. Allocator-level rollback
        on space exhaustion is handled by the lower layers.

        ``access`` defaults to ``"LR/R"``; ``date`` defaults to
        today's date.
        """
        import datetime

        from oaknut.afs.access import AFSAccess
        from oaknut.afs.types import AfsDate

        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot write_bytes to the root directory")
        if access is None:
            # ACCDEF at Uade01:271 — owner R+W, no public access,
            # unlocked. Matches what the ROM's create path defaults to.
            access = AFSAccess.from_string("WR/")
        elif isinstance(access, int) and not isinstance(access, AFSAccess):
            access = AFSAccess.from_byte(access)
        if date is None:
            date = AfsDate(datetime.date.today())

        parent_sin, name = afs._resolve_parent_and_name(self)
        afs._write_file(
            parent_sin,
            name,
            data,
            load_address=load_address,
            exec_address=exec_address,
            access=access,
            date=date,
        )

    def mkdir(
        self,
        *,
        access=None,
        date=None,
    ) -> None:
        """Create an empty directory at this path.

        A directory is an object whose data is a valid empty
        directory byte image (DRENTS=0, free list spanning every
        slot, trailing seq byte matching leading). Its access byte
        has the directory-type bit set.
        """
        import datetime

        from oaknut.afs.access import AFSAccess
        from oaknut.afs.directory import build_directory_bytes
        from oaknut.afs.types import AfsDate

        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot mkdir the root directory")
        if access is None:
            access = AFSAccess.from_string("D/")
        if date is None:
            date = AfsDate(datetime.date.today())

        parent_sin, name = afs._resolve_parent_and_name(self)

        # A fresh directory: default 2-sector, 19-slot capacity,
        # name = the final path component, seq = 0.
        dir_bytes = build_directory_bytes(
            name=name,
            master_sequence_number=0,
            entries=[],
            size_in_bytes=512,
        )
        afs._write_file(
            parent_sin,
            name,
            dir_bytes,
            load_address=0,
            exec_address=0,
            access=access,
            date=date,
        )

    def unlink(self) -> None:
        """Delete this file (or empty directory) from its parent.

        Frees the underlying object's sectors and removes the
        directory entry. Refuses non-empty directories, matching
        ``DELCHK`` at ``Uade0D:1218``.
        """
        from oaknut.afs.directory import AfsDirectory, delete_entry
        from oaknut.afs.exceptions import AFSDirectoryNotEmptyError, AFSFileLockedError

        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot unlink the root directory")
        parent_sin, name = afs._resolve_parent_and_name(self)
        parent_raw = afs._read_object_bytes(parent_sin)
        parent_dir = AfsDirectory.from_bytes(parent_raw)
        entry = parent_dir[name]
        if entry.is_locked:
            raise AFSFileLockedError(f"{self} is locked (L bit set)")
        if entry.is_directory:
            child_raw = afs._read_object_bytes(entry.sin)
            child_dir = AfsDirectory.from_bytes(child_raw)
            if len(child_dir) > 0:
                raise AFSDirectoryNotEmptyError(f"{self} is not empty ({len(child_dir)} entries)")
        afs._delete_object(entry.sin)
        new_parent = delete_entry(parent_raw, name)
        afs._write_object_bytes(parent_sin, new_parent)

    def rmdir(self) -> None:
        """Alias for :meth:`unlink` — the empty-dir check is shared."""
        self.unlink()

    # ------------------------------------------------------------------
    # Entry-field updates
    # ------------------------------------------------------------------

    def chmod(self, access: "int | AFSAccess") -> None:
        """Set the access attributes of this file or directory.

        ``access`` may be:

        - an :class:`AFSAccess` — used directly (disc bit layout).
        - an ``int`` — interpreted as an :class:`oaknut.file.Access`
          (wire / NFS bit layout, matching
          :meth:`ADFSPath.chmod`) and translated to the AFS on-disc
          layout.  Bits that have no AFS counterpart (``E``) are
          silently dropped.

        The :attr:`AFSAccess.DIRECTORY` bit is always forced to
        match the object's actual type; ``chmod`` cannot convert a
        file to a directory or vice versa.
        """
        from oaknut.afs.access import AFSAccess
        from oaknut.afs.directory import update_entry_fields

        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot chmod the root directory")

        new_access = _coerce_access(access)

        _, entry = afs._resolve(self)
        if entry.is_directory:
            new_access |= AFSAccess.DIRECTORY
        else:
            new_access &= ~AFSAccess.DIRECTORY

        parent_sin, name = afs._resolve_parent_and_name(self)
        parent_raw = afs._read_object_bytes(parent_sin)
        new_parent = update_entry_fields(parent_raw, name, access=new_access)
        afs._write_object_bytes(parent_sin, new_parent)

    def lock(self) -> None:
        """Set the ``L`` (locked) bit, preserving all other flags."""
        from oaknut.afs.access import AFSAccess

        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot lock the root directory")
        _, entry = afs._resolve(self)
        self.chmod(entry.access | AFSAccess.LOCKED)

    def unlock(self) -> None:
        """Clear the ``L`` (locked) bit, preserving all other flags."""
        from oaknut.afs.access import AFSAccess

        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot unlock the root directory")
        _, entry = afs._resolve(self)
        self.chmod(entry.access & ~AFSAccess.LOCKED)

    def set_load_address(self, address: int) -> None:
        """Rewrite this entry's load address without touching its data."""
        from oaknut.afs.directory import update_entry_fields

        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot set_load_address on the root directory")
        parent_sin, name = afs._resolve_parent_and_name(self)
        parent_raw = afs._read_object_bytes(parent_sin)
        new_parent = update_entry_fields(parent_raw, name, load_address=address)
        afs._write_object_bytes(parent_sin, new_parent)

    def set_exec_address(self, address: int) -> None:
        """Rewrite this entry's exec address without touching its data."""
        from oaknut.afs.directory import update_entry_fields

        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot set_exec_address on the root directory")
        parent_sin, name = afs._resolve_parent_and_name(self)
        parent_raw = afs._read_object_bytes(parent_sin)
        new_parent = update_entry_fields(parent_raw, name, exec_address=address)
        afs._write_object_bytes(parent_sin, new_parent)

    def rename(self, target: "str | AFSPath") -> AFSPath:
        """Rename or move this entry to ``target``, returning the new path.

        ``target`` must be an absolute path: a string starting with
        ``$`` or an :class:`AFSPath` with an absolute ``parts``.
        Moving across directories is supported — the underlying
        object's data is not rewritten; only the directory entry
        changes parent.
        """
        from oaknut.afs.directory import (
            DirectoryEntry,
            delete_entry,
            insert_entry,
            rename_entry,
        )

        afs = self._require_afs()
        if self.is_root():
            raise AFSPathError("cannot rename the root directory")

        if isinstance(target, AFSPath):
            target_path = target
        else:
            target_path = AFSPath.parse(target)
        if not target_path.is_absolute():
            raise AFSPathError(
                f"rename target {target!r} must be an absolute path starting at {ROOT!r}"
            )
        target_bound = AFSPath(target_path.parts, afs=afs)

        src_parent_sin, src_name = afs._resolve_parent_and_name(self)
        dst_parent_sin, dst_name = afs._resolve_parent_and_name(target_bound)

        if src_parent_sin == dst_parent_sin:
            # Same-directory rename: a single in-place slot update.
            parent_raw = afs._read_object_bytes(src_parent_sin)
            new_parent = rename_entry(parent_raw, src_name, dst_name)
            afs._write_object_bytes(src_parent_sin, new_parent)
            return target_bound

        # Cross-directory move: insert into the destination first,
        # then remove from the source.  If the insert fails, the
        # source is untouched; if the delete fails after a successful
        # insert, the user is left with an entry referencing the SIN
        # from both parents — but we have no transactional backend
        # to guard against that.
        src_parent_raw = afs._read_object_bytes(src_parent_sin)
        _, src_entry = afs._resolve(self)
        renamed_entry = DirectoryEntry(
            name=dst_name,
            load_address=src_entry.load_address,
            exec_address=src_entry.exec_address,
            access=src_entry.access,
            date=src_entry.date,
            sin=src_entry.sin,
        )
        dst_parent_raw = afs._read_object_bytes(dst_parent_sin)
        new_dst_parent = insert_entry(dst_parent_raw, renamed_entry)
        afs._write_object_bytes(dst_parent_sin, new_dst_parent)
        new_src_parent = delete_entry(src_parent_raw, src_name)
        afs._write_object_bytes(src_parent_sin, new_src_parent)
        return target_bound


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_access(access: "int | AFSAccess") -> "AFSAccess":
    """Normalise a ``chmod`` argument to an :class:`AFSAccess`.

    An :class:`AFSAccess` is used directly; any other ``int`` is
    interpreted as an :class:`oaknut.file.Access` (wire / NFS bit
    layout) and translated to the on-disc AFS layout.
    """
    from oaknut.afs.access import AFSAccess
    from oaknut.file import Access as WireAccess

    if isinstance(access, AFSAccess):
        return access
    wire = WireAccess(int(access))
    result = AFSAccess(0)
    if wire & WireAccess.L:
        result |= AFSAccess.LOCKED
    if wire & WireAccess.R:
        result |= AFSAccess.OWNER_READ
    if wire & WireAccess.W:
        result |= AFSAccess.OWNER_WRITE
    if wire & WireAccess.PR:
        result |= AFSAccess.PUBLIC_READ
    if wire & WireAccess.PW:
        result |= AFSAccess.PUBLIC_WRITE
    # Access.E has no AFS equivalent; silently dropped.
    return result

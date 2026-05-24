"""Shared base class for Acorn-filesystem path objects.

Modelled on ``pathlib.PurePath``/``pathlib.Path``: a concrete base
that defines the uniform path-object surface every Acorn filesystem
exposes, with filesystem-specific primitives left to concrete
subclasses (:class:`oaknut.dfs.DFSPath`, :class:`oaknut.adfs.ADFSPath`,
:class:`oaknut.afs.AFSPath`).

The filesystem-agnostic operations — :meth:`__iter__`, :meth:`walk`,
:meth:`read_text`, :meth:`write_text`, :meth:`touch`, :meth:`copy_to` —
have default implementations on the base; subclasses only have to
implement the primitives (:meth:`read_bytes`, :meth:`write_bytes`,
:meth:`stat`, :meth:`iterdir`, :meth:`exists`, :meth:`is_dir`).

Callers wanting "a path on any Acorn filesystem" can type-hint with
:class:`AcornPath` instead of spelling a union.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from oaknut.file.access import Access
    from oaknut.file.exceptions import FSError
    from oaknut.file.stat import Stat


class AcornPath:
    """Concrete base for DFSPath, ADFSPath, and AFSPath.

    Inheriting concrete classes set the class attributes
    :attr:`EntryExistsError` and :attr:`DirectoryError` so the
    shared :meth:`touch` default raises the right filesystem-specific
    exception. Otherwise subclasses only need to implement the
    abstract primitives below.
    """

    # Subclasses set these to the filesystem-specific FSError subclasses.
    EntryExistsError: "type[FSError]"
    DirectoryError: "type[FSError]"

    # ------------------------------------------------------------------
    # Abstract navigation primitives
    # ------------------------------------------------------------------

    def __truediv__(self, name: str) -> "AcornPath":
        """Join a child component, returning a new path."""
        raise NotImplementedError

    @property
    def parent(self) -> "AcornPath":
        """The containing path. The root's parent is the root itself."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        """The final path component."""
        raise NotImplementedError

    @property
    def parts(self) -> tuple[str, ...]:
        """Path components as a tuple."""
        raise NotImplementedError

    @property
    def path(self) -> str:
        """The full path string."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Abstract querying primitives
    # ------------------------------------------------------------------

    def exists(self) -> bool:
        """Whether something exists at this path."""
        raise NotImplementedError

    def is_dir(self) -> bool:
        """Whether this path resolves to a directory."""
        raise NotImplementedError

    def is_file(self) -> bool:
        """Whether this path resolves to a file."""
        raise NotImplementedError

    def stat(self) -> "Stat":
        """Return file metadata as an :class:`oaknut.file.Stat`."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Abstract iteration primitive
    # ------------------------------------------------------------------

    def iterdir(self) -> "Iterator[AcornPath]":
        """Yield the immediate children of this directory."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Abstract I/O primitives
    # ------------------------------------------------------------------

    def read_bytes(self) -> bytes:
        """Read this file's raw bytes."""
        raise NotImplementedError

    def write_bytes(
        self,
        data: bytes,
        *,
        load_address: int = 0,
        exec_address: int = 0,
        access: "Access | None" = None,
        date: object = None,
    ) -> None:
        """Write *data* to this path with the given metadata."""
        raise NotImplementedError

    def rename(self, target: "str | AcornPath") -> "AcornPath":
        """Rename this entry; return the new path."""
        raise NotImplementedError

    def unlink(self) -> None:
        """Delete the file (or empty directory) at this path."""
        raise NotImplementedError

    def lock(self) -> None:
        """Set the locked bit on this entry."""
        raise NotImplementedError

    def unlock(self) -> None:
        """Clear the locked bit on this entry."""
        raise NotImplementedError

    def set_load_address(self, address: int) -> None:
        """Set the load address of this file."""
        raise NotImplementedError

    def set_exec_address(self, address: int) -> None:
        """Set the execution address of this file."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Default implementations
    # ------------------------------------------------------------------

    def __iter__(self) -> "Iterator[AcornPath]":
        return self.iterdir()

    def walk(self) -> "Iterator[tuple[AcornPath, list[str], list[str]]]":
        """Pre-order walk yielding ``(dirpath, dirnames, filenames)``.

        Mirrors :meth:`pathlib.Path.walk`. Descends into every
        subdirectory; leaf directories yield a single tuple with
        empty ``dirnames``.
        """
        children = list(self.iterdir())
        dirnames: list[str] = []
        filenames: list[str] = []
        for child in children:
            (dirnames if child.is_dir() else filenames).append(child.name)
        yield self, dirnames, filenames
        for dirname in dirnames:
            yield from (self / dirname).walk()

    def read_text(
        self,
        *,
        encoding: str = "acorn",
        newline: str | None = None,
    ) -> str:
        """Read file contents as text via :func:`oaknut.file.decode_text`."""
        from oaknut.file.text_io import decode_text

        return decode_text(self.read_bytes(), encoding=encoding, newline=newline)

    def write_text(
        self,
        text: str,
        *,
        encoding: str = "acorn",
        newline: str | None = "\r",
        load_address: int = 0,
        exec_address: int = 0,
        access: "Access | None" = None,
        date: object = None,
    ) -> None:
        """Write text via :func:`oaknut.file.encode_text` + :meth:`write_bytes`."""
        from oaknut.file.text_io import encode_text

        self.write_bytes(
            encode_text(text, encoding=encoding, newline=newline),
            load_address=load_address,
            exec_address=exec_address,
            access=access,
            date=date,
        )

    def touch(
        self,
        *,
        access: "Access | None" = None,
        exist_ok: bool = True,
    ) -> None:
        """Create an empty file at this path; mirrors :meth:`pathlib.Path.touch`.

        Raises :attr:`DirectoryError` when a directory already
        exists at this path, and :attr:`EntryExistsError` when a
        file exists and ``exist_ok`` is ``False``.
        """
        if self.exists():
            if self.is_dir():
                raise self.DirectoryError(
                    f"{self.path!r} is a directory, cannot touch"
                )
            if exist_ok:
                return
            raise self.EntryExistsError(
                f"{self.path!r} already exists"
            )
        self.write_bytes(b"", access=access)

    def copy_to(self, dst: "AcornPath") -> None:
        """Copy this file's bytes and metadata to *dst*.

        Sugar for :func:`oaknut.file.copy_file`. The destination may
        live on any Acorn filesystem family.
        """
        from oaknut.file.copy import copy_file

        copy_file(self, dst)

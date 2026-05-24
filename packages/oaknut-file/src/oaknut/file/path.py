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

from functools import wraps
from typing import TYPE_CHECKING, Callable, Iterator, TypeVar

if TYPE_CHECKING:
    from oaknut.file.access import Access
    from oaknut.file.exceptions import FSError
    from oaknut.file.stat import Stat


_F = TypeVar("_F", bound=Callable)


def resolving_io(method: _F) -> _F:
    """Decorator: resolve ``^`` components before calling an I/O method.

    Wraps a path-class I/O method so any literal carets stored in
    the path are collapsed via :meth:`AcornPath.resolve` before the
    underlying body runs. If the path has no carets, the call goes
    straight through.

    Apply to every method on a concrete path class whose answer
    depends on the disc — :meth:`read_bytes`, :meth:`exists`,
    :meth:`stat`, :meth:`iterdir`, and the rest. Pure path ops
    (``__str__``, :attr:`parts`, :attr:`parent`) stay un-decorated
    because they should preserve the literal form.
    """

    @wraps(method)
    def wrapper(self: AcornPath, *args, **kwargs):
        resolved = self.resolve()
        if resolved is not self:
            return getattr(resolved, method.__name__)(*args, **kwargs)
        return method(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


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

    #: Whether this path type can carry a directory *title* (a
    #: human-readable label distinct from the name). Only ADFS
    #: directories can; DFS and AFS directories cannot. Callers that
    #: want to fail before mutating (e.g. ``mkdir --title``) check
    #: this flag rather than catching :class:`TitleNotSupportedError`
    #: after the fact.
    supports_title: bool = False

    # ------------------------------------------------------------------
    # Abstract navigation primitives
    # ------------------------------------------------------------------

    def __truediv__(self, name: str) -> "AcornPath":
        """Slash-join a path fragment, returning a new path.

        Splits *name* on ``.`` and appends each component literally
        via :meth:`_join_name`. The Acorn shell's ``^`` parent
        token is stored as a literal path component too — call
        :meth:`resolve` to collapse ``^`` runs against their
        preceding directories. This mirrors :class:`pathlib.PurePath`
        which stores ``..`` literally rather than resolving on join.

        Examples::

            p / "Games" / "Elite"      # join two names
            p / "Games.Elite"          # equivalent, single string
            p / "^"                    # literal ^ component; resolve()
                                       # collapses it to p.parent
            p / "^^.Docs.ReadMe"       # ^^ stored as one component;
                                       # resolve() walks up two then in
        """
        path: "AcornPath" = self
        for component in name.split("."):
            if not component:
                continue
            path = path._join_name(component)
        return path

    def resolve(self) -> "AcornPath":
        """Collapse any ``^`` components against their preceding parts.

        Returns a new path with every caret component (``^``,
        ``^^``, ``^^^`` …) removed, after walking one directory up
        per caret character. Carets that would walk past the root
        clamp at the root, mirroring :attr:`parent`'s behaviour.

        Pure operation — does not touch the filesystem. ``^`` is
        reserved Acorn syntax and cannot appear in a legitimate
        on-disc name, so I/O methods call ``resolve()`` automatically
        before reading or writing.
        """
        resolved: list[str] = list(self._root_parts())
        for part in self.parts[len(self._root_parts()):]:
            if set(part) == {"^"}:
                for _ in part:
                    if len(resolved) > len(self._root_parts()):
                        resolved.pop()
                    # else: clamp at root
            else:
                resolved.append(part)
        if tuple(resolved) == self.parts:
            return self
        path = self._root()
        for part in resolved[len(self._root_parts()):]:
            path = path._join_name(part)
        return path

    def _root(self) -> "AcornPath":
        """Return the root path of the filesystem this path is bound to.

        Subclasses implement this so :meth:`resolve` can reconstruct
        a path with carets collapsed by re-joining from the root.
        """
        raise NotImplementedError

    def _root_parts(self) -> tuple[str, ...]:
        """The ``parts`` tuple of the filesystem root.

        Empty for DFS (nameless root); ``("$",)`` for ADFS/AFS.
        Used by :meth:`resolve` to know where the joinable suffix
        begins.
        """
        raise NotImplementedError

    def _join_name(self, name: str) -> "AcornPath":
        """Append a single non-caret name component.

        Subclasses implement this with their filesystem-specific
        path-string construction. The default :meth:`__truediv__`
        delegates here once it has stripped out any leading
        carets, so subclasses never have to think about ``^``.
        """
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

    @property
    def title(self) -> str:
        """The directory's human-readable title.

        A title is distinct from the :attr:`name`: the name is the
        structural component used in paths, the title is a label
        stored inside the directory. Only ADFS directories have one,
        so the base implementation raises
        :class:`~oaknut.file.exceptions.TitleNotSupportedError`;
        :class:`oaknut.adfs.ADFSPath` overrides it.
        """
        from oaknut.file.exceptions import TitleNotSupportedError

        raise TitleNotSupportedError(
            "this filesystem's directories do not have a title"
        )

    @title.setter
    def title(self, value: str) -> None:
        from oaknut.file.exceptions import TitleNotSupportedError

        raise TitleNotSupportedError(
            "this filesystem's directories do not have a title"
        )

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

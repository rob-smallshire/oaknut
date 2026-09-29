"""Named conventions for translating file access between filing systems.

Each filing system stores access its own way: DFS keeps a lone locked
bit, ADFS a set of attribute bits in each directory entry, AFS its own
byte layout, ROMFS a run-only flag. A :class:`AccessConvention` is the
one place a native representation is mapped to and from the canonical
:class:`~oaknut.file.Access` word, so every command that reads, copies
or shows a file applies the same rule. The design, including the
conventions planned for CP/M, DOS/FAT and host permissions, is in
``docs/dev/access-model.md``.

:func:`translate_access` holds the choices a copy makes on top of those
facts — granting public access, applying a user's ``--access`` spec —
and returns the access the destination will actually hold.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Generic, TypeVar

from oaknut.file.access import Access

#: The native access representation a convention maps from and to.
Native = TypeVar("Native")


@dataclass(frozen=True)
class AccessContext:
    """What a convention may need to know about an object besides its access.

    Some rules depend on the kind of object: directories on most Acorn
    filing systems carry only the locked bit, and the UnixFS rules derive
    execute permission from a file's filetype.
    """

    is_directory: bool = False
    filetype: int | None = None


#: The context of an ordinary file.
FILE_CONTEXT = AccessContext()

#: The context of a directory.
DIRECTORY_CONTEXT = AccessContext(is_directory=True)


class AccessConvention(ABC, Generic[Native]):
    """A named mapping between one native access form and the canonical word.

    A subclass states facts about its filing system: which canonical bits
    it can hold (:attr:`representable`), and how its native value reads
    as and is written from an :class:`~oaknut.file.Access`. It makes no
    policy choices; those belong to :func:`translate_access`.
    """

    #: Identifies the convention, e.g. ``"acorn-dfs"``.
    name: ClassVar[str]
    #: The native representation family. Conventions sharing a family
    #: store access the same way.
    family: ClassVar[str]
    #: The canonical bits a native value can represent.
    representable: ClassVar[Access]
    #: Where the rules come from: a format description, a disassembly, a
    #: BeebWiki table.
    source: ClassVar[str]

    @abstractmethod
    def to_canonical(self, native: Native, context: AccessContext = FILE_CONTEXT) -> Access:
        """Read a native access value as the canonical word."""

    @abstractmethod
    def from_canonical(
        self,
        access: Access,
        context: AccessContext = FILE_CONTEXT,
        current: Native | None = None,
    ) -> Native:
        """Write the canonical word as a native value.

        Bits the canonical word cannot express (for example the ADFS
        private bit) are taken from *current*, the object's existing
        native value, when one is given.
        """

    def settle(self, access: Access, context: AccessContext = FILE_CONTEXT) -> Access:
        """The canonical access this convention would hold if given *access*."""
        return self.to_canonical(self.from_canonical(Access(access), context), context)


def _with_public(access: Access) -> Access:
    """*access* with the owner's read and write rights granted to the public."""
    granted = access
    if access & Access.R:
        granted |= Access.PR
    if access & Access.W:
        granted |= Access.PW
    return granted


def translate_access(
    access: Access,
    *,
    destination: AccessConvention,
    context: AccessContext = FILE_CONTEXT,
    grant_public: bool = False,
    override: Callable[[Access], Access] | None = None,
    warn: Callable[[str], None] | None = None,
) -> Access:
    """The access a file copied with *access* will hold on *destination*.

    *access* is the source's canonical access. With *grant_public* the
    owner's read and write rights are extended to the public (``WR`` to
    ``WR/WR``, ``LR`` to ``LR/R``). *override* — typically a transform
    from :func:`~oaknut.file.parse_access_spec` — is applied next.

    A run-only file (owner ``E`` without ``R``) copied to a destination
    that cannot store execute becomes readable instead: the copy
    protection cannot be kept, and a file no one can run or read is of no
    use. *warn*, when given, is called with a message saying so.

    The result is then settled by the destination convention, so it
    reports what the destination can actually store.
    """
    result = Access(access)
    if grant_public:
        result = _with_public(result)
    if override is not None:
        result = override(result)
    if result.is_run_only and not destination.representable & Access.E:
        result = (result & ~Access.E) | Access.R
        if warn is not None:
            warn(
                f"run-only access cannot be stored on {destination.name}, "
                "so the file is readable there instead"
            )
    return destination.settle(result, context)

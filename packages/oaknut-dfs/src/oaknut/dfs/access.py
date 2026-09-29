"""The Acorn DFS access convention.

A DFS catalogue records one access bit per file: the lock flag, bit 7 of
the entry's directory byte. Acorn DFS, Watford DFS and Opus DDOS share
that representation. This module is the single place it is mapped to and
from the canonical :class:`~oaknut.file.Access` word; see
``docs/dev/access-model.md``.
"""

from __future__ import annotations

from oaknut.file import FILE_CONTEXT, Access, AccessContext, AccessConvention


class AcornDFSAccessConvention(AccessConvention[bool]):
    """DFS access: a lone locked flag.

    Reading gives owner read and write, plus ``L`` when locked. Writing
    keeps only the lock bit (``attr AND &08``); DFS has nowhere to store
    the rest.
    """

    name = "acorn-dfs"
    family = "acorn-dfs"
    representable = Access.L | Access.R | Access.W
    source = (
        "BeebWiki, File access (DFS): https://beebwiki.mdfs.net/File_access#DFS; "
        "J.G. Harston, https://stardot.org.uk/forums/viewtopic.php?p=493553"
    )

    def to_canonical(self, native: bool, context: AccessContext = FILE_CONTEXT) -> Access:
        access = Access.R | Access.W
        if native:
            access |= Access.L
        return access

    def from_canonical(
        self,
        access: Access,
        context: AccessContext = FILE_CONTEXT,
        current: bool | None = None,
    ) -> bool:
        return bool(Access(access) & Access.L)


#: The shared instance used by the DFS path API and mount.
ACORN_DFS_ACCESS = AcornDFSAccessConvention()

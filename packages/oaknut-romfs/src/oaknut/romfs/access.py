"""The ROMFS access convention.

A ROMFS (and cassette filing system) file carries one access bit: block
flag bit 0, the ``*RUN``-only copy protection. This module is the single
place it is mapped to and from the canonical :class:`~oaknut.file.Access`
word; see ``docs/dev/access-model.md``.
"""

from __future__ import annotations

from oaknut.file import FILE_CONTEXT, Access, AccessContext, AccessConvention


class AcornROMFSAccessConvention(AccessConvention[bool]):
    """ROMFS access: the ``*RUN``-only flag, as :attr:`Access.X`.

    Run-only is its own axis, distinct from the disc filing systems'
    delete-lock ``L``: a locked DFS file copied onto a ROM must not
    become unloadable. An ordinary file reads as no access.
    """

    name = "acorn-romfs"
    family = "acorn-romfs"
    representable = Access.X
    source = "CFS/ROMFS block flag bit 0; MOS 1.20 checkFileAttributes"

    def to_canonical(self, native: bool, context: AccessContext = FILE_CONTEXT) -> Access:
        return Access.X if native else Access(0)

    def from_canonical(
        self,
        access: Access,
        context: AccessContext = FILE_CONTEXT,
        current: bool | None = None,
    ) -> bool:
        return bool(Access(access) & Access.X)


#: The shared instance used by the ROMFS mount.
ACORN_ROMFS_ACCESS = AcornROMFSAccessConvention()

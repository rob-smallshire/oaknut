"""The ROMFS access convention.

A ROMFS (and cassette filing system) file carries one access bit: block
flag bit 0, the ``*RUN``-only copy protection. This module is the single
place it is mapped to and from the canonical :class:`~oaknut.file.Access`
word; see ``docs/dev/access-model.md``.
"""

from __future__ import annotations

from oaknut.file import FILE_CONTEXT, Access, AccessContext, AccessConvention


class AcornROMFSAccessConvention(AccessConvention[bool]):
    """ROMFS access: readable, or ``*RUN``-only.

    An ordinary file reads as owner read (``R``). A run-only file reads as
    owner execute without read (``E``), the Acorn access byte's own
    representation of run-only (BeebWiki, *File access*). Writing makes a
    file run-only exactly when the access is run-only, so the disc filing
    systems' delete-lock ``L`` never does: a locked DFS file copied onto a
    ROM stays loadable.
    """

    name = "acorn-romfs"
    family = "acorn-romfs"
    representable = Access.R | Access.E
    source = (
        "CFS/ROMFS block flag bit 0; MOS 1.20 checkFileAttributes; "
        "BeebWiki, File access (run-only is E without R)"
    )

    def to_canonical(self, native: bool, context: AccessContext = FILE_CONTEXT) -> Access:
        return Access.E if native else Access.R

    def from_canonical(
        self,
        access: Access,
        context: AccessContext = FILE_CONTEXT,
        current: bool | None = None,
    ) -> bool:
        return Access(access).is_run_only


#: The shared instance used by the ROMFS mount.
ACORN_ROMFS_ACCESS = AcornROMFSAccessConvention()

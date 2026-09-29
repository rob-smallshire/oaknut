"""The ADFS access convention.

An ADFS directory entry carries its attributes as individual bits: owner
read, write, execute and locked; public read, write and execute; plus
the directory and private bits. This module is the single place those
bits are mapped to and from the canonical :class:`~oaknut.file.Access`
word; see ``docs/dev/access-model.md``.
"""

from __future__ import annotations

from oaknut.adfs.directory import _ADFSRawAttributes
from oaknut.file import FILE_CONTEXT, Access, AccessContext, AccessConvention


class ADFSAccessConvention(AccessConvention[_ADFSRawAttributes]):
    """ADFS access: owner R/W/E/L and public R/W map to the canonical bits.

    Public execute, the private bit and the directory bit have no place
    in the canonical word yet, so reading drops them and writing keeps
    them from the entry's current attributes.
    """

    name = "adfs"
    family = "adfs"
    representable = Access.R | Access.W | Access.E | Access.L | Access.PR | Access.PW
    source = "Acorn ADFS directory formats; BeebWiki, File access"

    def to_canonical(
        self, native: _ADFSRawAttributes, context: AccessContext = FILE_CONTEXT
    ) -> Access:
        access = Access(0)
        if native.owner_read:
            access |= Access.R
        if native.owner_write:
            access |= Access.W
        if native.owner_execute:
            access |= Access.E
        if native.locked:
            access |= Access.L
        if native.public_read:
            access |= Access.PR
        if native.public_write:
            access |= Access.PW
        return access

    def from_canonical(
        self,
        access: Access,
        context: AccessContext = FILE_CONTEXT,
        current: _ADFSRawAttributes | None = None,
    ) -> _ADFSRawAttributes:
        access = Access(access)
        return _ADFSRawAttributes(
            owner_read=bool(access & Access.R),
            owner_write=bool(access & Access.W),
            locked=bool(access & Access.L),
            directory=current.directory if current is not None else context.is_directory,
            owner_execute=bool(access & Access.E),
            public_read=bool(access & Access.PR),
            public_write=bool(access & Access.PW),
            public_execute=current.public_execute if current is not None else False,
            private=current.private if current is not None else False,
        )


#: The shared instance used by the ADFS path API and mount.
ADFS_ACCESS = ADFSAccessConvention()

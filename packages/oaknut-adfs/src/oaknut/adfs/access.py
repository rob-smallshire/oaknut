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
    """ADFS access: owner R/W/E/L and public R/W/E map to the canonical bits.

    The private bit is canonical bit 7, ``PL``. The directory bit says
    what an object is rather than who may use it, so writing keeps it
    from the entry's current attributes.
    """

    name = "adfs"
    family = "adfs"
    representable = (
        Access.R | Access.W | Access.E | Access.L | Access.PR | Access.PW | Access.PE | Access.PL
    )
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
        if native.public_execute:
            access |= Access.PE
        if native.private:
            access |= Access.PL
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
            public_execute=bool(access & Access.PE),
            private=bool(access & Access.PL),
        )


class ADFSNewDirectoryAccessConvention(ADFSAccessConvention):
    """ADFS access in New and Big directories (D, E, F, E+ and F+ formats).

    The ``NewDirAtts`` byte stores owner read, write and locked, public
    read and write, and the directory bit — but no owner execute, public
    execute or private bit. Writing therefore drops ``E``, ``PE`` and
    ``PL``, so a run-only file cannot be represented.
    """

    name = "adfs-new-directory"
    family = "adfs-new-directory"
    representable = Access.R | Access.W | Access.L | Access.PR | Access.PW
    source = "RISC OS FileCore New/Big directory formats (NewDirAtts)"

    def from_canonical(
        self,
        access: Access,
        context: AccessContext = FILE_CONTEXT,
        current: _ADFSRawAttributes | None = None,
    ) -> _ADFSRawAttributes:
        raw = super().from_canonical(access, context, current)
        return _ADFSRawAttributes(
            owner_read=raw.owner_read,
            owner_write=raw.owner_write,
            locked=raw.locked,
            directory=raw.directory,
            owner_execute=False,
            public_read=raw.public_read,
            public_write=raw.public_write,
            public_execute=False,
            private=False,
        )


#: The shared instance for old-format directories (S, M and L formats).
ADFS_ACCESS = ADFSAccessConvention()

#: The shared instance for New and Big directories.
ADFS_NEW_DIRECTORY_ACCESS = ADFSNewDirectoryAccessConvention()

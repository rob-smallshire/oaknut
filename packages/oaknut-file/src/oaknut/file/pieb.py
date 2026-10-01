"""The PiEconetBridge access convention.

PiEconetBridge stores a file's permissions in its own ``perm`` byte, in
the fourth field of its INF sidecar and in the ``user.econet_perm``
extended attribute. The byte is not the Acorn access byte: the lock and
execute bits are swapped, and bit 7 marks a hidden file. From
PiEconetBridge ``utilities/fs.c``::

    #define FS_PERM_H 0x80     // Hidden
    #define FS_PERM_OTH_W 0x20 // Write by others
    #define FS_PERM_OTH_R 0x10 // Read by others
    #define FS_PERM_EXEC 0x08  // Execute only
    #define FS_PERM_L 0x04     // Locked
    #define FS_PERM_OWN_W 0x02 // Write by owner
    #define FS_PERM_OWN_R 0x01 // Read by owner

This module maps that byte to and from the canonical
:class:`~oaknut.file.Access` word; see ``docs/dev/access-model.md``.
"""

from __future__ import annotations

from oaknut.file.access import Access
from oaknut.file.access_convention import FILE_CONTEXT, AccessContext, AccessConvention

_PERM_OWNER_READ = 0x01
_PERM_OWNER_WRITE = 0x02
_PERM_LOCKED = 0x04
_PERM_EXECUTE_ONLY = 0x08
_PERM_OTHER_READ = 0x10
_PERM_OTHER_WRITE = 0x20
_PERM_HIDDEN = 0x80

#: PiEconetBridge's default permission for a new file, ``WR/R``.
PIEB_DEFAULT_PERM = _PERM_OWNER_READ | _PERM_OWNER_WRITE | _PERM_OTHER_READ


class PiEconetBridgeAccessConvention(AccessConvention[int]):
    """PiEconetBridge ``perm``: owner and other R/W, locked, execute-only, hidden.

    Owner and other read and write map to the canonical owner and public
    bits. The PiEB lock bit (``0x04``) is ``L``; its execute-only bit
    (``0x08``) is run-only, owner ``E`` without ``R``; its hidden bit
    (``0x80``) is the ``HIDDEN`` attribute.
    """

    name = "pieb"
    family = "pieb"
    representable = (
        Access.R | Access.W | Access.E | Access.L | Access.PR | Access.PW | Access.HIDDEN
    )
    source = "PiEconetBridge utilities/fs.c (FS_PERM_*)"

    def to_canonical(self, native: int, context: AccessContext = FILE_CONTEXT) -> Access:
        access = Access(0)
        if native & _PERM_OWNER_READ:
            access |= Access.R
        if native & _PERM_OWNER_WRITE:
            access |= Access.W
        if native & _PERM_LOCKED:
            access |= Access.L
        if native & _PERM_EXECUTE_ONLY:
            access |= Access.E
        if native & _PERM_OTHER_READ:
            access |= Access.PR
        if native & _PERM_OTHER_WRITE:
            access |= Access.PW
        if native & _PERM_HIDDEN:
            access |= Access.HIDDEN
        return access

    def from_canonical(
        self,
        access: Access,
        context: AccessContext = FILE_CONTEXT,
        current: int | None = None,
    ) -> int:
        access = Access(access)
        perm = 0
        if access & Access.R:
            perm |= _PERM_OWNER_READ
        if access & Access.W:
            perm |= _PERM_OWNER_WRITE
        if access & Access.L:
            perm |= _PERM_LOCKED
        if access.is_run_only:
            perm |= _PERM_EXECUTE_ONLY
        if access & Access.PR:
            perm |= _PERM_OTHER_READ
        if access & Access.PW:
            perm |= _PERM_OTHER_WRITE
        if access & Access.HIDDEN:
            perm |= _PERM_HIDDEN
        return perm


#: The shared instance used by the PiEconetBridge INF and xattr formats.
PIEB_ACCESS = PiEconetBridgeAccessConvention()

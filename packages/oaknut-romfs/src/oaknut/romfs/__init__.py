"""Acorn ROM Filing System (ROMFS).

ROMFS is Acorn's filing system for *paged ROMs* — the sideways ROM and
cartridge format used on the BBC Micro and Acorn Electron. It stores
files in the same block layout as the Cassette Filing System (CFS): the
backing store is simply a linear ROM image rather than a tape, so a
file is a chain of CFS-format blocks (load/exec addresses, block number,
length, flag byte, header and data CRCs) preceded by a standard paged-ROM
service header.

Because the medium is read-only ROM the filing system is flat — there are
no directories — and a file's metadata is the Acorn load/exec pair plus a
lock bit, exactly as on cassette. This package adapts that on-ROM format
to the :mod:`oaknut.filesystem` extension contract so ROMFS images are
identifiable, listable and readable through the ``disc`` CLI alongside the
disc-based filing systems.

See ``docs/romfs-format-spec.md`` for the on-ROM byte layout and
``docs/architecture.md`` for how the native API maps onto the
``oaknut.filesystem`` plug-in interface.
"""

from __future__ import annotations

from oaknut.romfs.crc import crc16_ccitt
from oaknut.romfs.exceptions import (
    CRCError,
    NotAROMFSError,
    ROMFSError,
    ROMFullError,
    TruncatedROMError,
)
from oaknut.romfs.romfs import ROMFS, ROMFSFile

__version__ = "12.3.0"

__all__ = [
    "ROMFS",
    "ROMFSFile",
    "ROMFSError",
    "NotAROMFSError",
    "CRCError",
    "TruncatedROMError",
    "ROMFullError",
    "crc16_ccitt",
]

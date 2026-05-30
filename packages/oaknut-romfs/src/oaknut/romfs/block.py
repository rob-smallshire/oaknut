"""The CFS block-header codec — parse and serialise one ROMFS block.

A ROMFS file is a chain of Cassette Filing System blocks. A *header
block* begins with the sync byte ``&2A`` followed by the fields modelled
by :class:`BlockHeader`; *continuation* blocks within a multi-block file
use a single ``&23`` marker instead of a header and are implicitly 256
data bytes. The filing system ends with a single ``&2B`` byte.

This module owns the byte-level header format (field layout, flag bits,
CRC placement). Walking a chain into files and assembling files into a
chain lives one layer up, in :mod:`oaknut.romfs.romfs`. See
``docs/romfs-format-spec.md`` §2.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from oaknut.romfs.crc import crc16_ccitt
from oaknut.romfs.exceptions import CRCError, TruncatedROMError

#: A header block starts with this synchronisation byte (``'*'``).
SYNC_BYTE = 0x2A
#: A continuation (data-only) block within a multi-block file (``'#'``).
INTER_BLOCK_MARKER = 0x23
#: A single byte marking the end of the filing-system data (``'+'``).
END_OF_FILESYSTEM = 0x2B

#: Flag bit: this is the last block of its file.
FLAG_LAST = 0x80
#: Flag bit: this block carries no data (mkromfs sets it; Acorn does not —
#: test ``block_length == 0`` rather than this bit to detect an empty file).
FLAG_EMPTY = 0x40
#: Flag bit: the file is locked.
FLAG_LOCKED = 0x01

#: Maximum file-name length (characters), excluding the NUL terminator.
MAX_NAME_LENGTH = 10
#: A full block carries this many data bytes; a continuation block always does.
BLOCK_DATA_SIZE = 256

# Fixed-size part of the header following the NUL-terminated name:
# load (4), exec (4), block number (2), block length (2), flag (1),
# end-of-file address (4). The two-byte header CRC follows.
_FIXED = struct.Struct("<IIHHBI")


@dataclass(frozen=True)
class BlockHeader:
    """The header of one CFS block, in decoded form.

    The multi-byte integer fields are stored little-endian on the ROM; the
    trailing header CRC (handled by :meth:`to_bytes` / :meth:`parse`) is
    stored big-endian. *end_address* is the paged-ROM address of the byte
    just past this file — i.e. where the next file begins.
    """

    name: str
    load_address: int
    exec_address: int
    block_number: int
    block_length: int
    flag: int
    end_address: int

    @property
    def is_last(self) -> bool:
        """Whether this is the final block of its file (flag bit 7)."""
        return bool(self.flag & FLAG_LAST)

    @property
    def is_empty(self) -> bool:
        """Whether the block carries no data (length 0)."""
        return self.block_length == 0

    @property
    def is_locked(self) -> bool:
        """Whether the file is locked (flag bit 0)."""
        return bool(self.flag & FLAG_LOCKED)

    def field_bytes(self) -> bytes:
        """The header bytes the CRC is taken over: name through end address.

        This is everything after the sync byte and before the header CRC.
        """
        return (
            self.name.encode("latin-1")
            + b"\x00"
            + _FIXED.pack(
                self.load_address,
                self.exec_address,
                self.block_number,
                self.block_length,
                self.flag,
                self.end_address,
            )
        )

    def to_bytes(self) -> bytes:
        """The full on-ROM header: sync byte, fields, big-endian header CRC."""
        fields = self.field_bytes()
        crc = crc16_ccitt(fields)
        return bytes([SYNC_BYTE]) + fields + crc.to_bytes(2, "big")

    @classmethod
    def parse(cls, buf, offset: int = 0) -> tuple["BlockHeader", int]:
        """Parse a header block at *offset* (which must hold the sync byte).

        Returns ``(header, data_offset)`` where *data_offset* is the offset
        of the block's data, just past the two-byte header CRC. Raises
        :class:`CRCError` if the stored header CRC does not match, and
        :class:`TruncatedROMError` if the buffer ends mid-header.
        """
        view = memoryview(buf)
        if offset >= len(view) or view[offset] != SYNC_BYTE:
            raise TruncatedROMError(f"no block sync byte at offset {offset}")
        name_start = offset + 1
        nul = buf.find(b"\x00", name_start)
        if nul < 0:
            raise TruncatedROMError("unterminated block-header name")
        fixed_start = nul + 1
        crc_start = fixed_start + _FIXED.size
        crc_end = crc_start + 2
        if crc_end > len(view):
            raise TruncatedROMError("block header runs past the end of the ROM")
        name = bytes(view[name_start:nul]).decode("latin-1")
        load, execa, block_number, block_length, flag, end_address = _FIXED.unpack(
            view[fixed_start:crc_start]
        )
        stored_crc = int.from_bytes(view[crc_start:crc_end], "big")
        computed = crc16_ccitt(view[name_start:crc_start])
        if stored_crc != computed:
            raise CRCError(
                f"header CRC mismatch for {name!r}: "
                f"stored &{stored_crc:04X}, computed &{computed:04X}"
            )
        header = cls(name, load, execa, block_number, block_length, flag, end_address)
        return header, crc_end

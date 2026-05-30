"""The native ROMFS API: parse a paged-ROM image into its files.

:class:`ROMFS` is the user-facing class. It parses the paged-ROM header
(type byte, title, version, copyright) and walks the Cassette Filing
System block chain into a flat list of :class:`ROMFSFile` objects,
verifying every header and data CRC. The medium is a flat ROM image, so
there are no directories.

The class keeps the original image preamble (header plus service handler)
and the offset at which the filing-system data starts, so the serialiser
(:mod:`oaknut.romfs` write path) can rebuild the whole ≤16 KiB image while
preserving the machine-code prefix it does not model. See
``docs/romfs-format-spec.md``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from oaknut.romfs.block import (
    BLOCK_DATA_SIZE,
    END_OF_FILESYSTEM,
    INTER_BLOCK_MARKER,
    SYNC_BYTE,
    BlockHeader,
)
from oaknut.romfs.crc import crc16_ccitt
from oaknut.romfs.exceptions import CRCError, NotAROMFSError, TruncatedROMError

# Paged-ROM header offsets (relative to the ROM base, conventionally &8000).
_ROM_TYPE_OFFSET = 6
_COPYRIGHT_PTR_OFFSET = 7
_VERSION_OFFSET = 8
_TITLE_OFFSET = 9
#: ROM type bit 7: a service entry is present (set by every ROMFS ROM).
_SERVICE_ENTRY_BIT = 0x80


@dataclass(frozen=True)
class ROMFSFile:
    """One file stored in a ROMFS image.

    *data* is the whole file, reassembled across its blocks. *end_address*
    is the paged-ROM address just past the file, as stored in its headers.
    """

    name: str
    load_address: int
    exec_address: int
    locked: bool
    data: bytes
    end_address: int = 0

    @property
    def length(self) -> int:
        """The file length in bytes (the ``*.`` total-length column)."""
        return len(self.data)

    @property
    def last_block_number(self) -> int:
        """The block number of the file's final block (the ``*.`` first column).

        Equals the number of 256-byte blocks minus one; zero for an empty
        file or any file of 256 bytes or fewer.
        """
        if self.length == 0:
            return 0
        return (self.length - 1) // BLOCK_DATA_SIZE

    @property
    def is_title(self) -> bool:
        """Whether this is a ``*…*``-wrapped, zero-length title block."""
        return (
            self.length == 0
            and len(self.name) >= 2
            and self.name[0] == "*"
            and self.name[-1] == "*"
        )


def _decode_string(buf: bytes, start: int) -> str:
    """Decode a NUL-terminated latin-1 string starting at *start*."""
    end = buf.find(b"\x00", start)
    if end < 0:
        raise TruncatedROMError("unterminated string in ROM header")
    return buf[start:end].decode("latin-1")


def _find_data_start(buf: bytes) -> int:
    """Offset of the first ``&2A`` whose block header CRC validates.

    The filing-system data follows a hand-written service handler of
    ROM-specific length, so its start cannot be assumed at a fixed offset;
    it is located by scanning for the first well-formed block.
    """
    pos = buf.find(bytes([SYNC_BYTE]), _TITLE_OFFSET)
    while pos >= 0:
        try:
            BlockHeader.parse(buf, pos)
            return pos
        except (CRCError, TruncatedROMError):
            pass
        pos = buf.find(bytes([SYNC_BYTE]), pos + 1)
    raise NotAROMFSError("no valid ROMFS block found in image")


def _iter_blocks(buf: bytes, start: int) -> Iterator[tuple[BlockHeader | None, bytes]]:
    """Yield ``(header_or_None, data)`` for each block from *start*.

    A header block yields its :class:`BlockHeader`; a ``&23`` continuation
    block yields ``None`` and its 256 data bytes. Stops at ``&2B``. Every
    data CRC is verified.
    """
    pos = start
    while pos < len(buf):
        marker = buf[pos]
        if marker == END_OF_FILESYSTEM:
            return
        if marker == SYNC_BYTE:
            header, data_offset = BlockHeader.parse(buf, pos)
            data, pos = _read_data(buf, data_offset, header.block_length)
            yield header, data
        elif marker == INTER_BLOCK_MARKER:
            data, pos = _read_data(buf, pos + 1, BLOCK_DATA_SIZE)
            yield None, data
        else:
            raise TruncatedROMError(
                f"expected a block marker at offset {pos}, found &{marker:02X}"
            )


def _read_data(buf: bytes, offset: int, length: int) -> tuple[bytes, int]:
    """Read *length* data bytes at *offset*, verify the data CRC, return next pos.

    A zero-length block carries no data and no CRC.
    """
    if length == 0:
        return b"", offset
    end = offset + length
    if end + 2 > len(buf):
        raise TruncatedROMError("block data runs past the end of the ROM")
    data = bytes(buf[offset:end])
    stored = int.from_bytes(buf[end : end + 2], "big")
    computed = crc16_ccitt(data)
    if stored != computed:
        raise CRCError(f"data CRC mismatch: stored &{stored:04X}, computed &{computed:04X}")
    return data, end + 2


def _assemble_files(buf: bytes, start: int) -> list[ROMFSFile]:
    """Group the block stream from *start* into whole files."""
    files: list[ROMFSFile] = []
    name = load = execa = end_address = 0
    locked = False
    chunks: list[bytes] = []
    open_file = False

    for header, data in _iter_blocks(buf, start):
        if header is not None and header.block_number == 0:
            if open_file:
                raise TruncatedROMError(f"file {name!r} did not end before the next began")
            name, load, execa = header.name, header.load_address, header.exec_address
            locked, end_address = header.is_locked, header.end_address
            chunks = [data]
            open_file = True
        else:
            if not open_file:
                raise TruncatedROMError("continuation block with no file in progress")
            chunks.append(data)
        if header is not None and header.is_last:
            files.append(
                ROMFSFile(name, load, execa, locked, b"".join(chunks), end_address)
            )
            open_file = False

    if open_file:
        raise TruncatedROMError(f"file {name!r} has no final block")
    return files


class ROMFS:
    """An Acorn ROM Filing System image, parsed into its files."""

    def __init__(
        self,
        files: tuple[ROMFSFile, ...],
        *,
        rom_type: int,
        header_title: str,
        version: int,
        copyright: str,
        image: bytes,
        data_offset: int,
    ):
        self._files = tuple(files)
        self._rom_type = rom_type
        self._header_title = header_title
        self._version = version
        self._copyright = copyright
        self._image = bytes(image)
        self._data_offset = data_offset

    @classmethod
    def from_bytes(cls, buf) -> "ROMFS":
        """Parse a ROMFS image from *buf* (bytes-like).

        Raises :class:`NotAROMFSError` if no valid ROMFS block is found and
        :class:`CRCError` / :class:`TruncatedROMError` on a corrupt chain.
        """
        image = bytes(buf)
        if len(image) <= _TITLE_OFFSET:
            raise NotAROMFSError("image too small to be a paged ROM")
        data_offset = _find_data_start(image)
        files = _assemble_files(image, data_offset)
        return cls(
            tuple(files),
            rom_type=image[_ROM_TYPE_OFFSET],
            header_title=_decode_string(image, _TITLE_OFFSET),
            version=image[_VERSION_OFFSET],
            copyright=_decode_string(image, image[_COPYRIGHT_PTR_OFFSET] + 1),
            image=image,
            data_offset=data_offset,
        )

    @property
    def files(self) -> tuple[ROMFSFile, ...]:
        """All files in catalogue order, including any ``*…*`` title block."""
        return self._files

    @property
    def rom_type(self) -> int:
        """The paged-ROM type byte (bit 7 set marks the service entry)."""
        return self._rom_type

    @property
    def has_service_entry(self) -> bool:
        """Whether the ROM type byte advertises a service entry."""
        return bool(self._rom_type & _SERVICE_ENTRY_BIT)

    @property
    def header_title(self) -> str:
        """The paged-ROM header title (shown by ``*HELP``)."""
        return self._header_title

    @property
    def version(self) -> int:
        """The binary version byte from the paged-ROM header."""
        return self._version

    @property
    def copyright(self) -> str:
        """The paged-ROM copyright string (begins ``(C)``)."""
        return self._copyright

    @property
    def title(self) -> str:
        """The filing-system title (the ``*…*`` title block, unwrapped).

        Empty when the image has no title block (as on the BBC Zalaga ROM),
        which is the title ``*.`` displays.
        """
        if self._files and self._files[0].is_title:
            return self._files[0].name[1:-1]
        return ""

    @property
    def data_offset(self) -> int:
        """Offset at which the filing-system data begins within the image."""
        return self._data_offset

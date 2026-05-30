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

from dataclasses import dataclass

from oaknut.romfs.block import (
    BLOCK_DATA_SIZE,
    END_OF_FILESYSTEM,
    FLAG_LAST,
    FLAG_LOCKED,
    INTER_BLOCK_MARKER,
    SYNC_BYTE,
    BlockHeader,
)
from oaknut.romfs.crc import crc16_ccitt
from oaknut.romfs.exceptions import (
    CRCError,
    NotAROMFSError,
    ROMFSError,
    ROMFullError,
    TruncatedROMError,
)

#: Paged ROMs are mapped at &8000; image offset 0 is this address.
ROM_BASE_ADDRESS = 0x8000

# Paged-ROM header offsets (relative to the ROM base, conventionally &8000).
_ROM_TYPE_OFFSET = 6
_COPYRIGHT_PTR_OFFSET = 7
_VERSION_OFFSET = 8
_TITLE_OFFSET = 9
#: ROM type bit 7: a service entry is present (set by every ROMFS ROM).
_SERVICE_ENTRY_BIT = 0x80
# Fixed header overhead per block: sync + name NUL + 17 fixed bytes + 2 CRC.
_HEADER_OVERHEAD = 1 + 1 + 17 + 2


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



def _unwrap_title(name: str) -> str:
    """Strip the surrounding asterisks from an Acornsoft-style title block."""
    if len(name) >= 2 and name[0] == "*" and name[-1] == "*":
        return name[1:-1]
    return name


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


def _assemble_files(buf: bytes, start: int) -> tuple[list[ROMFSFile], bool, int]:
    """Walk the block chain from *start* into whole files.

    Returns ``(files, complete, end)``. *complete* is True only when the
    chain ended cleanly at the ``&2B`` marker; *end* is the offset just past
    it. When the data runs off the end of the ROM, or meets a non-marker
    byte where a block is expected — as a fragment of a multi-ROM filing
    system does, having no terminator — the walk stops, *complete* is False,
    *end* is where it stopped, and any dangling (partly-present) trailing
    file is discarded; the complete files before it are returned. A bad CRC
    is genuine corruption and still raises.
    """
    files: list[ROMFSFile] = []
    name = load = execa = end_address = 0
    locked = False
    chunks: list[bytes] = []
    open_file = False
    pos = start

    while pos < len(buf):
        marker = buf[pos]
        if marker == END_OF_FILESYSTEM:
            return files, True, pos + 1
        try:
            if marker == SYNC_BYTE:
                header, data_offset = BlockHeader.parse(buf, pos)
                data, pos = _read_data(buf, data_offset, header.block_length)
            elif marker == INTER_BLOCK_MARKER:
                header, (data, pos) = None, _read_data(buf, pos + 1, BLOCK_DATA_SIZE)
            else:
                break  # non-marker byte: no terminator here — an incomplete ROM
        except TruncatedROMError:
            break  # ran off the end mid-block — an incomplete (fragment) ROM

        if header is not None and header.block_number == 0:
            if open_file:
                break  # a new file began before the previous ended — stop, incomplete
            name, load, execa = header.name, header.load_address, header.exec_address
            locked, end_address = header.is_locked, header.end_address
            chunks = [data]
            open_file = True
        else:
            if not open_file:
                break  # continuation with no file in progress — stop, incomplete
            chunks.append(data)
        if header is not None and header.is_last:
            files.append(ROMFSFile(name, load, execa, locked, b"".join(chunks), end_address))
            open_file = False

    return files, False, pos


def _chain_length(name: str, data_length: int) -> int:
    """The on-ROM byte length of one file's block chain.

    Mirrors :func:`_serialise_file`: a header on the first and last blocks,
    a one-byte ``&23`` marker on the middle blocks, plus two CRC bytes per
    data block. An empty file is a single header block with no data.
    """
    header = len(name) + _HEADER_OVERHEAD
    if data_length == 0:
        return header
    blocks = (data_length + BLOCK_DATA_SIZE - 1) // BLOCK_DATA_SIZE
    total = 0
    for index in range(blocks):
        block_data = min(BLOCK_DATA_SIZE, data_length - index * BLOCK_DATA_SIZE)
        leader = header if (index == 0 or index == blocks - 1) else 1
        total += leader + block_data + 2
    return total


def _serialise_file(file: "ROMFSFile", end_address: int) -> bytes:
    """Encode one file's block chain (see ``docs/romfs-format-spec.md`` §2.4)."""
    flag_base = FLAG_LOCKED if file.locked else 0
    out = bytearray()
    if file.length == 0:
        header = BlockHeader(
            file.name,
            file.load_address,
            file.exec_address,
            0,
            0,
            FLAG_LAST | flag_base,
            end_address,
        )
        return header.to_bytes()
    blocks = (file.length + BLOCK_DATA_SIZE - 1) // BLOCK_DATA_SIZE
    for index in range(blocks):
        block_data = file.data[index * BLOCK_DATA_SIZE : (index + 1) * BLOCK_DATA_SIZE]
        is_last = index == blocks - 1
        if index == 0 or is_last:
            flag = flag_base | (FLAG_LAST if is_last else 0)
            header = BlockHeader(
                file.name,
                file.load_address,
                file.exec_address,
                index,
                len(block_data),
                flag,
                end_address,
            )
            out += header.to_bytes()
        else:
            out += bytes([INTER_BLOCK_MARKER])
        out += block_data
        out += crc16_ccitt(block_data).to_bytes(2, "big")
    return bytes(out)


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
        fs_end: int,
        complete: bool,
    ):
        self._files = tuple(files)
        self._rom_type = rom_type
        self._header_title = header_title
        self._version = version
        self._copyright = copyright
        self._image = bytes(image)
        self._data_offset = data_offset
        # Offset just past the original image's &2B end marker — fixed by the
        # source image and carried through with_files, so to_bytes can locate
        # the original padding run and any opaque trailing content.
        self._fs_end = fs_end
        self._complete = complete

    @classmethod
    def from_bytes(cls, buf) -> "ROMFS":
        """Parse a ROMFS image from *buf* (bytes-like).

        Raises :class:`NotAROMFSError` if no valid ROMFS block is found, and
        :class:`CRCError` on a corrupt block. A ROM with no ``&2B``
        terminator — a fragment of a multi-ROM filing system, or a truncated
        image — does **not** raise: it parses to an *incomplete* ROMFS
        (:attr:`is_complete` is False) holding the complete files it could
        read, with any dangling trailing file dropped.
        """
        image = bytes(buf)
        if len(image) <= _TITLE_OFFSET:
            raise NotAROMFSError("image too small to be a paged ROM")
        data_offset = _find_data_start(image)
        files, complete, fs_end = _assemble_files(image, data_offset)
        return cls(
            tuple(files),
            rom_type=image[_ROM_TYPE_OFFSET],
            header_title=_decode_string(image, _TITLE_OFFSET),
            version=image[_VERSION_OFFSET],
            copyright=_decode_string(image, image[_COPYRIGHT_PTR_OFFSET] + 1),
            image=image,
            data_offset=data_offset,
            fs_end=fs_end,
            complete=complete,
        )

    @property
    def files(self) -> tuple[ROMFSFile, ...]:
        """All files in catalogue order, including any leading title block."""
        return self._files

    @property
    def title_block(self) -> ROMFSFile | None:
        """The leading zero-length title block, or ``None``.

        By convention the first file is a zero-length marker naming the
        disc. Acornsoft wraps the name in asterisks (``*Hopper01*``); the
        BBC Master demos use a bare name (``DEMO-A``); some ROMs (Zalaga)
        have none, beginning directly with a real file. Detection is
        therefore positional — a zero-length *first* file — not name-based.
        """
        if self._files and self._files[0].length == 0:
            return self._files[0]
        return None

    @property
    def data_files(self) -> tuple[ROMFSFile, ...]:
        """The files excluding any leading title block."""
        return self._files[1:] if self.title_block is not None else self._files

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
        block = self.title_block
        return _unwrap_title(block.name) if block is not None else ""

    @property
    def data_offset(self) -> int:
        """Offset at which the filing-system data begins within the image."""
        return self._data_offset

    @property
    def is_complete(self) -> bool:
        """Whether the filing system terminates within this ROM (a ``&2B``).

        False marks an *incomplete* image: the block chain ran to the end of
        the ROM without a terminator. That is how a non-final fragment of a
        multi-ROM filing system looks (its data continues in the socket
        below), and also how a truncated image looks — the two are
        indistinguishable from one ROM alone. Either way the image is read
        as far as its complete files and is treated as read-only, since it
        is part of (or a damaged) larger whole. Multi-ROM reassembly is not
        supported; see ``docs/romfs-format-spec.md`` §7.
        """
        return self._complete

    @property
    def is_plain(self) -> bool:
        """Whether nothing but padding follows the filing system.

        A *plain* ROMFS holds only the filing system: everything after the
        ``&2B`` end marker is a single padding byte to the end of the ROM. A
        *composite* ROM carries opaque content after the filing system —
        typically a service handler answering ``*HELP`` (service call &09)
        or a co-resident language. The writer preserves that content, and
        the mount treats a composite ROM as read-only to avoid corrupting
        it. See ``docs/romfs-format-spec.md``.
        """
        _, opaque_start = self._suffix_layout(self._fs_end)
        return opaque_start >= len(self._image)

    def with_files(self, files: tuple[ROMFSFile, ...]) -> "ROMFS":
        """A copy with its files replaced, keeping the same ROM container.

        The header/handler prefix, header metadata and image size are
        carried over; :meth:`to_bytes` lays the new chain out within the
        same ROM, so the result re-parses as the same kind of image.
        """
        return ROMFS(
            tuple(files),
            rom_type=self._rom_type,
            header_title=self._header_title,
            version=self._version,
            copyright=self._copyright,
            image=self._image,
            data_offset=self._data_offset,
            fs_end=self._fs_end,
            complete=self._complete,
        )

    def to_bytes(self) -> bytes:
        """Serialise to a whole ROM image of the original size.

        The header/handler prefix is preserved verbatim, the file chain and
        ``&2B`` end marker are rebuilt, and any opaque trailing content (a
        language ROM's code, as in Countdown To Doom) is kept at its
        original address. The padding run immediately after the original
        ``&2B`` is the only space the filing system may grow into; exceeding
        it raises :class:`ROMFullError`. An *incomplete* image cannot be
        serialised (there is no whole filing system to write back); that
        raises :class:`ROMFSError`.
        """
        if not self._complete:
            raise ROMFSError(
                "cannot serialise an incomplete ROMFS: it is a fragment of a "
                "multi-ROM filing system (or a truncated image), so there is no "
                "whole filing system to write back"
            )
        prefix = self._image[: self._data_offset]

        offset = self._data_offset
        parts: list[bytes] = []
        for file in self._files:
            chain_length = _chain_length(file.name, file.length)
            end_address = ROM_BASE_ADDRESS + offset + chain_length
            blob = _serialise_file(file, end_address)
            parts.append(blob)
            offset += chain_length
        new_fs_end = offset + 1  # the &2B end marker

        # The original image's layout after the FS: a padding run, then any
        # opaque trailing content (a language ROM's code).
        pad_byte, opaque_start = self._suffix_layout(self._fs_end)
        opaque = self._image[opaque_start:]

        if new_fs_end > opaque_start:
            overflow = new_fs_end - opaque_start
            raise ROMFullError(
                f"the filing system needs {overflow} byte(s) more than the ROM has free; "
                "it would overwrite content after the filing system"
            )

        body = b"".join(parts) + bytes([END_OF_FILESYSTEM])
        padding = bytes([pad_byte]) * (opaque_start - new_fs_end)
        return prefix + body + padding + opaque

    def _suffix_layout(self, original_fs_end: int) -> tuple[int, int]:
        """The padding byte and the offset where opaque trailing content begins.

        Free space is the run of a single byte value immediately following
        the original ``&2B``; anything after it is opaque and preserved.
        """
        if original_fs_end >= len(self._image):
            return 0xFF, len(self._image)
        pad_byte = self._image[original_fs_end]
        opaque_start = original_fs_end
        while opaque_start < len(self._image) and self._image[opaque_start] == pad_byte:
            opaque_start += 1
        return pad_byte, opaque_start

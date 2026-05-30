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
    MAX_NAME_LENGTH,
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
from oaknut.romfs.handler import build_rfs_handler, rfs_handler_length

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


#: The maximum title length: the title block is stored as ``*title*``, a
#: CFS name of at most MAX_NAME_LENGTH characters.
MAX_TITLE_LENGTH = MAX_NAME_LENGTH - 2

#: Default copyright for a created ROM (a valid Acorn copyright begins "(C)").
DEFAULT_COPYRIGHT = "(C) oaknut"


def _serialise_chain(files: tuple[ROMFSFile, ...], data_address: int) -> bytes:
    """The block chain for *files* laid out from *data_address* (no end marker)."""
    offset = 0
    parts: list[bytes] = []
    for file in files:
        chain_length = _chain_length(file.name, file.length)
        parts.append(_serialise_file(file, data_address + offset + chain_length))
        offset += chain_length
    return b"".join(parts)


def _assemble_image(
    *,
    header_title: str,
    copyright: str,
    version: int,
    files: tuple[ROMFSFile, ...],
    size: int,
    help_handler: bool,
) -> bytes:
    """Assemble a whole ROM image from a header, a handler and a file list.

    Lays out the paged-ROM header (a service-only ``&82`` ROM), the service
    handler, the file chain, the ``&2B`` end marker, and ``&FF`` padding to
    *size*. Shared by :func:`build_rom_image` and the copyright rebuild path.
    """
    if not copyright.startswith("(C)"):
        raise ROMFSError("a ROMFS copyright must begin with '(C)'")

    title_bytes = header_title.encode("latin-1")
    copyright_bytes = copyright.encode("latin-1")
    # Header: 00 00 00 | JMP service | type | copyoff | version | title NUL |
    # (no version string) | 00 copyright NUL. version_str is omitted (empty).
    header_length = 3 + 3 + 1 + 1 + 1 + len(title_bytes) + 1 + 1 + len(copyright_bytes) + 1
    service_address = ROM_BASE_ADDRESS + header_length
    data_address = service_address + rfs_handler_length(with_help=help_handler)
    copyright_offset = 9 + len(title_bytes) + 1  # offset of the 00 before "(C)"

    header = bytearray()
    header += b"\x00\x00\x00"  # null language entry
    header += bytes([0x4C, service_address & 0xFF, (service_address >> 8) & 0xFF])  # JMP service
    header += bytes([0x82])  # ROM type: service entry, 6502, no language
    header += bytes([copyright_offset])
    header += bytes([version & 0xFF])
    header += title_bytes + b"\x00"
    header += b"\x00" + copyright_bytes + b"\x00"
    assert len(header) == header_length

    handler = build_rfs_handler(service_address, data_address, with_help=help_handler)
    chain = _serialise_chain(files, data_address) + bytes([END_OF_FILESYSTEM])

    body = bytes(header) + handler + chain
    if len(body) > size:
        raise ROMFullError(
            f"ROM full: the contents need {len(body)} bytes, "
            f"more than the {size // 1024} KiB ROM holds"
        )
    return body + b"\xff" * (size - len(body))


def build_rom_image(
    *,
    title: str,
    copyright: str = DEFAULT_COPYRIGHT,
    version: int = 1,
    size: int = 16384,
    help_handler: bool = True,
) -> bytes:
    """Build a fresh, empty ROMFS paged-ROM image of *size* bytes.

    Lays out the standard header, the ``&0D``/``&0E`` service handler (so the
    ROM is readable on a real machine, see :mod:`oaknut.romfs.handler`), a
    single ``*title*`` title block, the ``&2B`` end marker, and ``&FF``
    padding. With *help_handler* the service code also answers ``*HELP``
    (``&09``) by printing the title. The result round-trips through
    :meth:`ROMFS.from_bytes` and is writable (plain and complete). *size* is
    8192 or 16384.
    """
    if not 1 <= len(title) <= MAX_TITLE_LENGTH:
        raise ROMFSError(f"a ROMFS title must be 1-{MAX_TITLE_LENGTH} characters: {title!r}")
    title_block = ROMFSFile(f"*{title}*", 0, 0, locked=True, data=b"")
    return _assemble_image(
        header_title=title,
        copyright=copyright,
        version=version,
        files=(title_block,),
        size=size,
        help_handler=help_handler,
    )


def get_copyright(image: bytes) -> str:
    """The copyright string of the ROMFS *image*."""
    return ROMFS.from_bytes(image).copyright


def get_version(image: bytes) -> int:
    """The binary version byte of the ROMFS *image*."""
    return ROMFS.from_bytes(image).version


def set_version(image: bytes, version: int) -> bytes:
    """A copy of *image* with the binary version byte set.

    The version is a single header byte (at ``&8008``), so this never moves
    anything; it is safe on any ROMFS image.
    """
    if not 0 <= version <= 0xFF:
        raise ROMFSError(f"a ROMFS version must be 0-255: {version}")
    ROMFS.from_bytes(image)  # validate it is a ROMFS
    out = bytearray(image)
    out[_VERSION_OFFSET] = version
    return bytes(out)


def set_copyright(image: bytes, text: str) -> bytes:
    """A copy of *image* with the copyright string set.

    A same-length string is overwritten in place (safe on any ROM). A
    different length moves the service handler, so the ROM is **rebuilt** —
    which regenerates the handler and is therefore only done for a ROM with
    no language entry and nothing after the filing system (a created ROM);
    other ROMs raise :class:`ROMFSError` rather than risk their code.
    """
    if not text.startswith("(C)"):
        raise ROMFSError("a ROMFS copyright must begin with '(C)'")
    rom = ROMFS.from_bytes(image)

    if len(text) == len(rom.copyright):
        out = bytearray(image)
        start = out[_COPYRIGHT_PTR_OFFSET] + 1  # past the leading NUL
        out[start : start + len(text)] = text.encode("latin-1")
        return bytes(out)

    if rom.rom_type & 0x40:  # bit 6: a language entry, whose code would move
        raise ROMFSError(
            "this ROM has a language entry, so changing the copyright length "
            "would relocate its code; set a same-length copyright, or recreate "
            "the ROM with `disc create`"
        )
    if not (rom.is_complete and rom.is_plain):
        raise ROMFSError(
            "this ROM carries code after the filing system (or is incomplete), "
            "so changing the copyright length is unsafe; set a same-length "
            "copyright instead"
        )
    return _assemble_image(
        header_title=rom.header_title,
        copyright=text,
        version=rom.version,
        files=rom.files,
        size=len(image),
        help_handler=True,
    )


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

        chain = _serialise_chain(self._files, ROM_BASE_ADDRESS + self._data_offset)
        new_fs_end = self._data_offset + len(chain) + 1  # the &2B end marker

        # The original image's layout after the FS: a padding run, then any
        # opaque trailing content (a language ROM's code).
        pad_byte, opaque_start = self._suffix_layout(self._fs_end)
        opaque = self._image[opaque_start:]

        if new_fs_end > opaque_start:
            overflow = new_fs_end - opaque_start
            byte_s = "byte" if overflow == 1 else "bytes"
            if opaque:
                # A composite ROM: the FS would run into the trailing code.
                raise ROMFullError(
                    f"ROM full: the filing system is {overflow} {byte_s} too large; "
                    f"it would overwrite the {len(opaque)}-byte program that follows it"
                )
            raise ROMFullError(
                f"ROM full: the filing system is {overflow} {byte_s} too large for "
                f"this {len(self._image) // 1024} KiB ROM"
            )

        body = chain + bytes([END_OF_FILESYSTEM])
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

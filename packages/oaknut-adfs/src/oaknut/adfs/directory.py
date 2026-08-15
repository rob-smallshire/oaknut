"""ADFS directory parsing — internal module.

Parses old-format ADFS directories (S/M/L) from raw sector data.
These types are private to the library; the public API exposes ADFSPath and ADFSStat.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from oaknut.adfs.exceptions import ADFSDirectoryError
from oaknut.discimage.sectors_view import SectorsView
from oaknut.file import Access  # re-exported for backward compatibility
from oaknut.filesystem import NameGrammar

__all__ = ["Access"]


#: What an ADFS directory entry's ten-byte name field can *hold and ADFS
#: can read back*, not what its command parser would accept — oaknut
#: manipulates discs that are legally representable, including the
#: parser-illegal names byte-edited onto game discs. The hard limits come
#: from the on-disc format (ADFS 1.30 disassembly): ten bytes maximum
#: (over-length is a "Bad name" error, not a truncation); each name byte
#: is seven-bit because bit 7 carries the file's access flags; and CR
#: terminates the field. The ``.`` / ``:`` separators are representable
#: but oaknut's dotted-path syntax cannot yet address them. Everything
#: else — wildcards, directory specials, spaces, control bytes — is
#: stored and read verbatim. Lives at the directory layer because that is
#: where names are stored and compared; ``adfs.py`` and ``filesystem.py``
#: import it from here. See :class:`oaknut.filesystem.NameGrammar`.
ADFS_NAME_GRAMMAR = NameGrammar(
    max_length=10,
    forbidden=".:\r",
    forbidden_reason="oaknut's . and : path separators, and CR (the field terminator)",
    seven_bit=True,
    allow_control=True,
    case="insensitive",
    codec="ascii",
    notes=(
        "Each name byte is seven-bit: bit 7 holds the file's access flags "
        "(R, W, L, D in bytes 0-3), so a name cannot carry an eighth bit.",
        "The field otherwise holds any byte, so oaknut stores and reads the "
        "parser-illegal names found on byte-edited discs — wildcards (* #), "
        "the directory specials ($ & @ ^ %), spaces and quotes. Reading "
        "never rejects a name.",
    ),
)

#: The name comparator for ADFS — see :data:`ADFS_NAME_GRAMMAR`.
_name_key = ADFS_NAME_GRAMMAR.name_key


#: What a **Big** directory (E+/F+/G) entry name can hold. Big directories keep
#: names in a heap, lifting the ten-character limit (to 255) and freeing the
#: top bit for eight-bit characters. The separators and CR are still reserved.
ADFS_BIG_NAME_GRAMMAR = NameGrammar(
    max_length=255,
    forbidden=".:\r",
    forbidden_reason="oaknut's . and : path separators, and CR (the field terminator)",
    seven_bit=False,
    allow_control=True,
    case="insensitive",
    codec="latin-1",
    notes=(
        "Big directories store filenames in a name heap, so names may be up to "
        "255 characters and use the full eight-bit Acorn Latin-1 character set.",
    ),
)


# --- Internal data types ---


@dataclass(frozen=True)
class _ADFSRawAttributes:
    """Raw attribute bits from a directory entry."""

    owner_read: bool
    owner_write: bool
    locked: bool
    directory: bool
    owner_execute: bool
    public_read: bool
    public_write: bool
    public_execute: bool
    private: bool


@dataclass(frozen=True)
class _ADFSDirectoryEntry:
    """Raw parsed directory entry — internal use only."""

    name: str
    load_address: int
    exec_address: int
    length: int
    indirect_disc_address: int
    sequence_number: int
    attributes: _ADFSRawAttributes

    @property
    def is_directory(self) -> bool:
        return self.attributes.directory

    @property
    def start_sector(self) -> int:
        """Sector number derived from indirect disc address.

        For old map discs, the indirect disc address IS the
        sector number (the DirIndDiscAdd field is named
        "Start Sector" in old format).
        """
        return self.indirect_disc_address


@dataclass(frozen=True)
class _ADFSDirectory:
    """Parsed directory block — internal use only."""

    name: str
    title: str
    parent_address: int
    disc_address: int
    entries: tuple[_ADFSDirectoryEntry, ...]
    sequence_number: int
    #: The directory's Hugo/Nick signature, preserved so an in-place rewrite
    #: does not flip it. ``b"Hugo"`` for S/M/L (and the D discs seen so far);
    #: ``b"Nick"`` for the New Map E/F shapes.
    signature: bytes = b"Hugo"
    #: For Big directories (E+/F+): the allocated byte size of the directory
    #: block, preserved across a rewrite. Zero for Old/New directories.
    big_dir_size: int = 0

    def find(self, name: str) -> _ADFSDirectoryEntry | None:
        """Find entry by name (per the grammar's case policy)."""
        target = _name_key(name)
        for entry in self.entries:
            if _name_key(entry.name) == target:
                return entry
        return None


# --- Directory format strategy ---


class ADFSDirectoryFormat(ABC):
    """Strategy for parsing different ADFS directory formats."""

    @abstractmethod
    def parse(self, data: SectorsView, disc_address: int) -> _ADFSDirectory:
        """Parse a directory from its on-disc data.

        Args:
            data: SectorsView covering the directory's sectors.
            disc_address: The disc address of this directory.

        Returns:
            Parsed directory structure.
        """
        ...

    @abstractmethod
    def serialize(self, directory: _ADFSDirectory, data: SectorsView) -> None:
        """Serialize a directory to its on-disc representation.

        Args:
            directory: The directory structure to serialize.
            data: SectorsView to write into (must be at least size_in_bytes).
        """
        ...

    @property
    @abstractmethod
    def size_in_bytes(self) -> int:
        """Size of a directory in bytes."""
        ...

    @property
    @abstractmethod
    def size_in_sectors(self) -> int:
        """Number of 256-byte sectors a directory occupies."""
        ...

    @property
    @abstractmethod
    def max_entries(self) -> int:
        """Maximum number of entries this format supports."""
        ...

    def directory_size(self, header: SectorsView) -> int:
        """Byte size of the directory whose header is in *header*.

        Fixed for Old/New directories; read from the header for Big
        directories, which vary in size.
        """
        return self.size_in_bytes

    def serialized_size(self, directory: _ADFSDirectory) -> int:
        """Byte size to write *directory* as. Fixed except for Big directories."""
        return self.size_in_bytes


# --- Old directory format (ADFS S/M/L) ---

# Old directory layout constants
_OLD_DIR_SIZE = 1280  # 5 sectors × 256 bytes
_OLD_DIR_SECTORS = 5
_OLD_DIR_MAX_ENTRIES = 47
_OLD_DIR_ENTRY_SIZE = 26
_OLD_DIR_HEADER_SIZE = 5  # StartMasSeq (1) + StartName (4)
_OLD_DIR_ENTRIES_OFFSET = _OLD_DIR_HEADER_SIZE  # 0x005

# Tail starts after header + max entries
_OLD_DIR_TAIL_OFFSET = _OLD_DIR_ENTRIES_OFFSET + _OLD_DIR_MAX_ENTRIES * _OLD_DIR_ENTRY_SIZE  # 0x4CB

# Tail field offsets (relative to tail start)
_OLD_TAIL_LAST_MARK = 0  # 1 byte
_OLD_TAIL_DIR_NAME = 1  # 10 bytes
_OLD_TAIL_PARENT = 11  # 3 bytes
_OLD_TAIL_TITLE = 14  # 19 bytes
_OLD_TAIL_RESERVED = 33  # 14 bytes
_OLD_TAIL_END_MAS_SEQ = 47  # 1 byte
_OLD_TAIL_END_NAME = 48  # 4 bytes
_OLD_TAIL_CHECK_BYTE = 52  # 1 byte

# Directory signatures
_HUGO = b"Hugo"
_NICK = b"Nick"


def _extract_old_attributes(name_bytes: bytes) -> _ADFSRawAttributes:
    """Extract attributes from top bits of old-format directory entry name.

    In old directories, attributes are stored in the top bit (bit 7)
    of each character in the 10-byte DirObName field:
      Char 0: R (owner read)
      Char 1: W (owner write)
      Char 2: L (locked)
      Char 3: D (directory)
      Char 4: E (owner execute-only)
      Char 5: r (public read)
      Char 6: w (public write)
      Char 7: e (public execute-only)
      Char 8: P (private)
      Char 9: not used
    """

    def bit7(b: int) -> bool:
        return bool(b & 0x80)

    return _ADFSRawAttributes(
        owner_read=bit7(name_bytes[0]),
        owner_write=bit7(name_bytes[1]),
        locked=bit7(name_bytes[2]),
        directory=bit7(name_bytes[3]),
        owner_execute=bit7(name_bytes[4]),
        public_read=bit7(name_bytes[5]),
        public_write=bit7(name_bytes[6]),
        public_execute=bit7(name_bytes[7]),
        private=bit7(name_bytes[8]),
    )


def _strip_name(name_bytes: bytes) -> str:
    """Extract filename from DirObName, stripping top bits.

    Names are terminated by the first CR (0x0D) or NUL (0x00) character.
    Bytes after the terminator are irrelevant (may contain garbage from
    a previous directory entry).
    """
    # Mask off top bit from each byte
    chars = bytes(b & 0x7F for b in name_bytes)
    # Truncate at first CR or NUL terminator
    for i, c in enumerate(chars):
        if c in (0x00, 0x0D):
            chars = chars[:i]
            break
    return chars.decode("ascii")


def _read_24bit_le(data: SectorsView | bytes, offset: int) -> int:
    """Read a 24-bit little-endian value."""
    return data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16)


def _write_24bit_le(data: SectorsView, offset: int, value: int) -> None:
    """Write a 24-bit little-endian value."""
    data[offset] = value & 0xFF
    data[offset + 1] = (value >> 8) & 0xFF
    data[offset + 2] = (value >> 16) & 0xFF


def _parse_old_entry(data: SectorsView, entry_offset: int) -> _ADFSDirectoryEntry | None:
    """Parse a single old-format directory entry.

    Returns None if this is the end-of-entries marker (first byte is 0).
    """
    # Check for end-of-entries marker
    if data[entry_offset] == 0:
        return None

    # Read 10-byte DirObName
    name_bytes = data[entry_offset : entry_offset + 10]
    attributes = _extract_old_attributes(name_bytes)
    name = _strip_name(name_bytes)

    # Read remaining fields (all little-endian)
    load_bytes = data[entry_offset + 0x0A : entry_offset + 0x0E]
    load_address = int.from_bytes(load_bytes, "little")

    exec_bytes = data[entry_offset + 0x0E : entry_offset + 0x12]
    exec_address = int.from_bytes(exec_bytes, "little")

    len_bytes = data[entry_offset + 0x12 : entry_offset + 0x16]
    length = int.from_bytes(len_bytes, "little")

    indirect_disc_address = _read_24bit_le(data, entry_offset + 0x16)
    sequence_number = data[entry_offset + 0x19]

    return _ADFSDirectoryEntry(
        name=name,
        load_address=load_address,
        exec_address=exec_address,
        length=length,
        indirect_disc_address=indirect_disc_address,
        sequence_number=sequence_number,
        attributes=attributes,
    )


def _serialize_old_entry(
    entry: _ADFSDirectoryEntry,
    data: SectorsView,
    entry_offset: int,
) -> None:
    """Serialize a single old-format directory entry at the given offset."""
    # Encode name (up to 10 chars, CR-padded)
    name_bytes = entry.name.encode("ascii")[:10].ljust(10, b"\r")

    # Set attribute bits in top bit of each name character
    attr_bits = [
        entry.attributes.owner_read,
        entry.attributes.owner_write,
        entry.attributes.locked,
        entry.attributes.directory,
        entry.attributes.owner_execute,
        entry.attributes.public_read,
        entry.attributes.public_write,
        entry.attributes.public_execute,
        entry.attributes.private,
        False,  # char 9 unused
    ]
    for i in range(10):
        data[entry_offset + i] = name_bytes[i] | (0x80 if attr_bits[i] else 0x00)

    # Load address (32-bit LE)
    for i in range(4):
        data[entry_offset + 0x0A + i] = (entry.load_address >> (i * 8)) & 0xFF

    # Exec address (32-bit LE)
    for i in range(4):
        data[entry_offset + 0x0E + i] = (entry.exec_address >> (i * 8)) & 0xFF

    # Length (32-bit LE)
    for i in range(4):
        data[entry_offset + 0x12 + i] = (entry.length >> (i * 8)) & 0xFF

    # Indirect disc address (24-bit LE)
    _write_24bit_le(data, entry_offset + 0x16, entry.indirect_disc_address)

    # Sequence number
    data[entry_offset + 0x19] = entry.sequence_number & 0xFF


class OldDirectoryFormat(ADFSDirectoryFormat):
    """Old ADFS directory format (S/M/L): 47 entries, 1280 bytes (5 sectors).

    Signature is "Hugo" at offset 0x01 and at the end of the tail.
    """

    @property
    def size_in_bytes(self) -> int:
        return _OLD_DIR_SIZE

    @property
    def size_in_sectors(self) -> int:
        return _OLD_DIR_SECTORS

    @property
    def max_entries(self) -> int:
        return _OLD_DIR_MAX_ENTRIES

    def parse(self, data: SectorsView, disc_address: int) -> _ADFSDirectory:
        """Parse an old-format directory from sector data."""
        if len(data) < _OLD_DIR_SIZE:
            raise ADFSDirectoryError(
                f"Directory data too short: {len(data)} bytes, need {_OLD_DIR_SIZE}"
            )

        # Validate header
        start_mas_seq = data[0x00]
        start_name = data[0x01:0x05]
        if start_name not in (_HUGO, _NICK):
            raise ADFSDirectoryError(
                f"Invalid directory signature: {start_name!r} (expected {_HUGO!r} or {_NICK!r})"
            )

        # Validate tail
        tail = _OLD_DIR_TAIL_OFFSET
        end_mas_seq = data[tail + _OLD_TAIL_END_MAS_SEQ]
        end_name = data[tail + _OLD_TAIL_END_NAME : tail + _OLD_TAIL_END_NAME + 4]

        if end_name != start_name:
            raise ADFSDirectoryError(
                f"Directory tail signature {end_name!r} does not match "
                f"header signature {start_name!r}"
            )

        if start_mas_seq != end_mas_seq:
            raise ADFSDirectoryError(
                f"Broken directory: StartMasSeq ({start_mas_seq}) != EndMasSeq ({end_mas_seq})"
            )

        # The DirCheckByte field is reserved (must be zero) on old-format
        # directories (S/M/L).  The checksum algorithm described in the PRM
        # applies only to new and big directory formats.
        expected_check = data[tail + _OLD_TAIL_CHECK_BYTE]
        if expected_check != 0:
            raise ADFSDirectoryError(
                f"Reserved check byte is 0x{expected_check:02X}, expected 0x00"
            )

        # Parse entries
        entries = []
        for i in range(_OLD_DIR_MAX_ENTRIES):
            entry_offset = _OLD_DIR_ENTRIES_OFFSET + i * _OLD_DIR_ENTRY_SIZE
            entry = _parse_old_entry(data, entry_offset)
            if entry is None:
                break
            entries.append(entry)

        # Parse tail fields
        dir_name_bytes = data[tail + _OLD_TAIL_DIR_NAME : tail + _OLD_TAIL_DIR_NAME + 10]
        dir_name = _strip_name(dir_name_bytes)

        parent_address = _read_24bit_le(data, tail + _OLD_TAIL_PARENT)

        title_bytes = data[tail + _OLD_TAIL_TITLE : tail + _OLD_TAIL_TITLE + 19]
        # _strip_name drops the CR/NUL padding ADFS terminates the field
        # with; trailing spaces (from a foreign writer) are padding too,
        # but internal spaces in a multi-word title must survive.
        title = _strip_name(title_bytes).rstrip(" ")

        return _ADFSDirectory(
            name=dir_name,
            title=title,
            parent_address=parent_address,
            disc_address=disc_address,
            entries=tuple(entries),
            sequence_number=start_mas_seq,
            signature=bytes(start_name),
        )

    def serialize(self, directory: _ADFSDirectory, data: SectorsView) -> None:
        """Serialize an old-format directory to sector data.

        Writes the complete 1280-byte directory block into *data*,
        including header, entries, and tail.
        """
        if len(data) < _OLD_DIR_SIZE:
            raise ADFSDirectoryError(
                f"Output data too short: {len(data)} bytes, need {_OLD_DIR_SIZE}"
            )
        if len(directory.entries) > _OLD_DIR_MAX_ENTRIES:
            raise ADFSDirectoryError(
                f"Too many entries: {len(directory.entries)}, maximum is {_OLD_DIR_MAX_ENTRIES}"
            )

        # Clear the buffer
        for i in range(_OLD_DIR_SIZE):
            data[i] = 0

        # Header. Old directories (S/M/L) are canonically "Hugo"; a "Nick"
        # read on a byte-edited disc is normalised back to "Hugo" on write.
        data[0x00] = directory.sequence_number & 0xFF
        data[0x01:0x05] = _HUGO

        # Entries
        for i, entry in enumerate(directory.entries):
            offset = _OLD_DIR_ENTRIES_OFFSET + i * _OLD_DIR_ENTRY_SIZE
            _serialize_old_entry(entry, data, offset)

        # End-of-entries marker (already zero from clearing)

        # Tail
        tail = _OLD_DIR_TAIL_OFFSET
        data[tail + _OLD_TAIL_LAST_MARK] = 0x00

        # Directory name (10 bytes, CR-padded)
        dir_name_bytes = directory.name.encode("ascii")[:10].ljust(10, b"\r")
        for i, b in enumerate(dir_name_bytes):
            data[tail + _OLD_TAIL_DIR_NAME + i] = b

        # Parent address (3 bytes LE)
        _write_24bit_le(data, tail + _OLD_TAIL_PARENT, directory.parent_address)

        # Title (19 bytes, CR-padded)
        title_bytes = directory.title.encode("ascii")[:19].ljust(19, b"\r")
        for i, b in enumerate(title_bytes):
            data[tail + _OLD_TAIL_TITLE + i] = b

        # Reserved (14 bytes) — already zero

        # EndMasSeq
        data[tail + _OLD_TAIL_END_MAS_SEQ] = directory.sequence_number & 0xFF
        # EndName
        data[tail + _OLD_TAIL_END_NAME : tail + _OLD_TAIL_END_NAME + 4] = _HUGO
        # DirCheckByte: reserved, must be zero
        data[tail + _OLD_TAIL_CHECK_BYTE] = 0x00


# --- New directory format (ADFS D/E/F) ---
#
# The New directory (2048 bytes, up to 77 entries) is the FileCore directory
# introduced with the D format and carried into the New Map E/F shapes. It
# differs from the Old directory in three ways that matter here:
#
#   * object attributes live in a dedicated NewDirAtts byte (entry+0x19), not
#     in the top bits of the name — so names may use all eight bits;
#   * the tail is laid out differently and is 0x29 (41) bytes long; and
#   * the DirCheckByte is a real ROR-13 checksum over the block, not a
#     reserved zero.
#
# For the D format the map remains the Old free-space map and DirIndDiscAdd is
# still a plain start sector, so file data is read contiguously exactly as for
# S/M/L. The New Map shapes reinterpret DirIndDiscAdd as a fragment address;
# that reinterpretation lives above this layer.

_NEW_DIR_SIZE = 2048  # 8 sectors × 256 bytes
_NEW_DIR_SECTORS = 8
_NEW_DIR_MAX_ENTRIES = 77
_NEW_DIR_ENTRY_SIZE = 26  # 0x1A — same entry shape as the Old directory
_NEW_DIR_HEADER_SIZE = 5  # StartMasSeq (1) + StartName (4)
_NEW_DIR_ENTRIES_OFFSET = _NEW_DIR_HEADER_SIZE  # 0x005

# Tail is a fixed 0x29 bytes at the end of the block.
_NEW_DIR_TAIL_SIZE = 0x29
_NEW_DIR_TAIL_OFFSET = _NEW_DIR_SIZE - _NEW_DIR_TAIL_SIZE  # 0x7D7

# Tail field offsets (relative to tail start)
_NEW_TAIL_LAST_MARK = 0x00  # 1 byte, 0 to mark end of entries
_NEW_TAIL_RESERVED = 0x01  # 2 bytes, must be zero
_NEW_TAIL_PARENT = 0x03  # 3 bytes, indirect disc address of parent
_NEW_TAIL_TITLE = 0x06  # 19 bytes, directory title
_NEW_TAIL_DIR_NAME = 0x19  # 10 bytes, directory name
_NEW_TAIL_END_MAS_SEQ = 0x23  # 1 byte, must match StartMasSeq
_NEW_TAIL_END_NAME = 0x24  # 4 bytes, must match StartName
_NEW_TAIL_CHECK_BYTE = 0x28  # 1 byte, ROR-13 directory checksum

# NewDirAtts bit meanings (entry offset 0x19). Bits 6-7 are reserved.
_NEW_ATT_OWNER_READ = 0x01
_NEW_ATT_OWNER_WRITE = 0x02
_NEW_ATT_LOCKED = 0x04
_NEW_ATT_DIRECTORY = 0x08
_NEW_ATT_PUBLIC_READ = 0x10
_NEW_ATT_PUBLIC_WRITE = 0x20


def _ror13(value: int) -> int:
    """Rotate a 32-bit value right by 13 bits."""
    return ((value >> 13) | (value << 19)) & 0xFFFFFFFF


def _read_32bit_le(data: SectorsView | bytes, offset: int) -> int:
    """Read a 32-bit little-endian value."""
    return (
        data[offset]
        | (data[offset + 1] << 8)
        | (data[offset + 2] << 16)
        | (data[offset + 3] << 24)
    )


def _strip_name_8bit(name_bytes: bytes) -> str:
    """Extract a New-directory name/title, preserving all eight bits.

    Unlike :func:`_strip_name`, the top bit is *not* masked — in New
    directories it is part of the character, not an attribute flag. The
    field is terminated by the first CR (0x0D) or NUL (0x00). Decoded as
    Latin-1 so no byte sequence can raise; real discs use 7-bit ASCII or
    the Acorn Latin-1 character set, both of which round-trip through it.
    """
    for i, c in enumerate(name_bytes):
        if c in (0x00, 0x0D):
            name_bytes = name_bytes[:i]
            break
    return bytes(name_bytes).decode("latin-1")


def _extract_new_attributes(atts: int) -> _ADFSRawAttributes:
    """Decode a NewDirAtts byte into raw attributes.

    New directories carry only R/W/L/D and public r/w; owner-execute,
    public-execute and private have no bit in this byte and are always
    reported as ``False``.
    """
    return _ADFSRawAttributes(
        owner_read=bool(atts & _NEW_ATT_OWNER_READ),
        owner_write=bool(atts & _NEW_ATT_OWNER_WRITE),
        locked=bool(atts & _NEW_ATT_LOCKED),
        directory=bool(atts & _NEW_ATT_DIRECTORY),
        owner_execute=False,
        public_read=bool(atts & _NEW_ATT_PUBLIC_READ),
        public_write=bool(atts & _NEW_ATT_PUBLIC_WRITE),
        public_execute=False,
        private=False,
    )


def _new_attributes_byte(attributes: _ADFSRawAttributes) -> int:
    """Encode raw attributes into a NewDirAtts byte."""
    byte = 0
    if attributes.owner_read:
        byte |= _NEW_ATT_OWNER_READ
    if attributes.owner_write:
        byte |= _NEW_ATT_OWNER_WRITE
    if attributes.locked:
        byte |= _NEW_ATT_LOCKED
    if attributes.directory:
        byte |= _NEW_ATT_DIRECTORY
    if attributes.public_read:
        byte |= _NEW_ATT_PUBLIC_READ
    if attributes.public_write:
        byte |= _NEW_ATT_PUBLIC_WRITE
    return byte


def _calculate_new_dir_check(data: SectorsView | bytes) -> int:
    """Compute the New-directory DirCheckByte (ROR-13 accumulation).

    Mirrors FileCore's algorithm (as implemented in Gerald Holdsworth's
    DiscImageManager ``CalculateADFSDirCheck``):

      1. Accumulate whole 32-bit words from the start of the block up to
         the end of the *used* entries (the first zero name-byte marks it).
      2. Accumulate the trailing <4 bytes of that region individually.
      3. Skip the first byte of the tail (to leave whole words), then
         accumulate the tail's whole words except the final word, which
         holds the check byte.
      4. XOR the four bytes of the accumulated word together.

    Each step folds a value in via ``dircheck = value XOR ROR13(dircheck)``.
    The unused entry slots between the end marker and the tail are not
    accumulated.
    """
    num_entries = 0
    while data[_NEW_DIR_ENTRIES_OFFSET + num_entries * _NEW_DIR_ENTRY_SIZE] != 0:
        num_entries += 1
    end_of_check = _NEW_DIR_ENTRIES_OFFSET + num_entries * _NEW_DIR_ENTRY_SIZE

    dircheck = 0
    amt = 0
    while amt + 3 < end_of_check:
        dircheck = _read_32bit_le(data, amt) ^ _ror13(dircheck)
        amt += 4
    while amt < end_of_check:
        dircheck = data[amt] ^ _ror13(dircheck)
        amt += 1

    amt = _NEW_DIR_TAIL_OFFSET + 1  # skip NewDirLastMark
    while amt + 3 < _NEW_DIR_SIZE - 4:
        dircheck = _read_32bit_le(data, amt) ^ _ror13(dircheck)
        amt += 4

    return (
        (dircheck & 0xFF)
        ^ ((dircheck >> 8) & 0xFF)
        ^ ((dircheck >> 16) & 0xFF)
        ^ ((dircheck >> 24) & 0xFF)
    )


def _parse_new_entry(data: SectorsView, entry_offset: int) -> _ADFSDirectoryEntry | None:
    """Parse a single New-directory entry.

    Returns None if this is the end-of-entries marker (first byte is 0).
    """
    if data[entry_offset] == 0:
        return None

    name_bytes = bytes(data[entry_offset : entry_offset + 10])
    name = _strip_name_8bit(name_bytes)

    load_address = _read_32bit_le(data, entry_offset + 0x0A)
    exec_address = _read_32bit_le(data, entry_offset + 0x0E)
    length = _read_32bit_le(data, entry_offset + 0x12)
    indirect_disc_address = _read_24bit_le(data, entry_offset + 0x16)
    atts_byte = data[entry_offset + 0x19]
    attributes = _extract_new_attributes(atts_byte)

    return _ADFSDirectoryEntry(
        name=name,
        load_address=load_address,
        exec_address=exec_address,
        length=length,
        indirect_disc_address=indirect_disc_address,
        sequence_number=0,
        attributes=attributes,
    )


def _serialize_new_entry(
    entry: _ADFSDirectoryEntry,
    data: SectorsView,
    entry_offset: int,
) -> None:
    """Serialize a single New-directory entry at the given offset."""
    # Name (up to 10 bytes, CR-padded, no attribute bits in the top bit).
    name_bytes = entry.name.encode("latin-1")[:10].ljust(10, b"\r")
    for i in range(10):
        data[entry_offset + i] = name_bytes[i]

    for i in range(4):
        data[entry_offset + 0x0A + i] = (entry.load_address >> (i * 8)) & 0xFF
    for i in range(4):
        data[entry_offset + 0x0E + i] = (entry.exec_address >> (i * 8)) & 0xFF
    for i in range(4):
        data[entry_offset + 0x12 + i] = (entry.length >> (i * 8)) & 0xFF
    _write_24bit_le(data, entry_offset + 0x16, entry.indirect_disc_address)
    data[entry_offset + 0x19] = _new_attributes_byte(entry.attributes)


class NewDirectoryFormat(ADFSDirectoryFormat):
    """New ADFS directory format (D/E/F): 77 entries, 2048 bytes (8 sectors).

    Signature is "Hugo" or "Nick" at offset 0x01 and in the tail, and the
    DirCheckByte is a real ROR-13 checksum.
    """

    @property
    def size_in_bytes(self) -> int:
        return _NEW_DIR_SIZE

    @property
    def size_in_sectors(self) -> int:
        return _NEW_DIR_SECTORS

    @property
    def max_entries(self) -> int:
        return _NEW_DIR_MAX_ENTRIES

    def parse(self, data: SectorsView, disc_address: int) -> _ADFSDirectory:
        """Parse a New-format directory from sector data."""
        if len(data) < _NEW_DIR_SIZE:
            raise ADFSDirectoryError(
                f"Directory data too short: {len(data)} bytes, need {_NEW_DIR_SIZE}"
            )

        start_mas_seq = data[0x00]
        start_name = bytes(data[0x01:0x05])
        if start_name not in (_HUGO, _NICK):
            raise ADFSDirectoryError(
                f"Invalid directory signature: {start_name!r} (expected {_HUGO!r} or {_NICK!r})"
            )

        tail = _NEW_DIR_TAIL_OFFSET
        end_mas_seq = data[tail + _NEW_TAIL_END_MAS_SEQ]
        end_name = bytes(data[tail + _NEW_TAIL_END_NAME : tail + _NEW_TAIL_END_NAME + 4])
        if end_name != start_name:
            raise ADFSDirectoryError(
                f"Directory tail signature {end_name!r} does not match "
                f"header signature {start_name!r}"
            )
        if start_mas_seq != end_mas_seq:
            raise ADFSDirectoryError(
                f"Broken directory: StartMasSeq ({start_mas_seq}) != EndMasSeq ({end_mas_seq})"
            )

        expected_check = data[tail + _NEW_TAIL_CHECK_BYTE]
        calculated_check = _calculate_new_dir_check(data)
        if expected_check != calculated_check:
            raise ADFSDirectoryError(
                f"Directory check byte mismatch: stored 0x{expected_check:02X}, "
                f"calculated 0x{calculated_check:02X}"
            )

        entries = []
        for i in range(_NEW_DIR_MAX_ENTRIES):
            entry_offset = _NEW_DIR_ENTRIES_OFFSET + i * _NEW_DIR_ENTRY_SIZE
            entry = _parse_new_entry(data, entry_offset)
            if entry is None:
                break
            entries.append(entry)

        dir_name = _strip_name_8bit(
            bytes(data[tail + _NEW_TAIL_DIR_NAME : tail + _NEW_TAIL_DIR_NAME + 10])
        )
        parent_address = _read_24bit_le(data, tail + _NEW_TAIL_PARENT)
        title = _strip_name_8bit(
            bytes(data[tail + _NEW_TAIL_TITLE : tail + _NEW_TAIL_TITLE + 19])
        ).rstrip(" ")

        return _ADFSDirectory(
            name=dir_name,
            title=title,
            parent_address=parent_address,
            disc_address=disc_address,
            entries=tuple(entries),
            sequence_number=start_mas_seq,
            signature=bytes(start_name),
        )

    def serialize(self, directory: _ADFSDirectory, data: SectorsView) -> None:
        """Serialize a New-format directory into *data* (2048 bytes)."""
        if len(data) < _NEW_DIR_SIZE:
            raise ADFSDirectoryError(
                f"Output data too short: {len(data)} bytes, need {_NEW_DIR_SIZE}"
            )
        if len(directory.entries) > _NEW_DIR_MAX_ENTRIES:
            raise ADFSDirectoryError(
                f"Too many entries: {len(directory.entries)}, maximum is {_NEW_DIR_MAX_ENTRIES}"
            )

        for i in range(_NEW_DIR_SIZE):
            data[i] = 0

        # Header. Preserve the directory's Hugo/Nick signature so an in-place
        # rewrite of a "Nick"-signed disc does not flip it; fall back to the
        # conventional "Hugo" for anything unexpected.
        signature = directory.signature if directory.signature in (_HUGO, _NICK) else _HUGO
        data[0x00] = directory.sequence_number & 0xFF
        data[0x01:0x05] = signature

        for i, entry in enumerate(directory.entries):
            offset = _NEW_DIR_ENTRIES_OFFSET + i * _NEW_DIR_ENTRY_SIZE
            _serialize_new_entry(entry, data, offset)

        tail = _NEW_DIR_TAIL_OFFSET
        data[tail + _NEW_TAIL_LAST_MARK] = 0x00

        dir_name_bytes = directory.name.encode("latin-1")[:10].ljust(10, b"\r")
        for i, b in enumerate(dir_name_bytes):
            data[tail + _NEW_TAIL_DIR_NAME + i] = b

        _write_24bit_le(data, tail + _NEW_TAIL_PARENT, directory.parent_address)

        title_bytes = directory.title.encode("latin-1")[:19].ljust(19, b"\r")
        for i, b in enumerate(title_bytes):
            data[tail + _NEW_TAIL_TITLE + i] = b

        data[tail + _NEW_TAIL_END_MAS_SEQ] = directory.sequence_number & 0xFF
        data[tail + _NEW_TAIL_END_NAME : tail + _NEW_TAIL_END_NAME + 4] = signature

        # DirCheckByte last — it is computed over everything else.
        data[tail + _NEW_TAIL_CHECK_BYTE] = _calculate_new_dir_check(data)


# --- Big directory format (ADFS E+/F+/G) ---
#
# Big directories lift the New directory's fixed size and 10-character name
# limit. The block is variable length (from 2048 bytes, growing as needed): a
# header (whose last field is the directory's own, arbitrarily long, name),
# then fixed 0x1C-byte entries that point into a following *name heap* for their
# filenames, then an 8-byte tail. Object indirect addresses are four bytes here.
# Signatures are "SBPr" (start) and "oven" (end); the check byte is the ROR-13
# accumulation with the Big-directory boundaries.

_BIG_DIR_START_NAME = b"SBPr"
_BIG_DIR_END_NAME = b"oven"
_BIG_DIR_HEADER_FIXED = 0x1C  # up to (and excluding) the directory name
_BIG_DIR_ENTRY_SIZE = 0x1C
_BIG_DIR_TAIL_SIZE = 8
_BIG_DIR_DEFAULT_SIZE = 2048


def _word_align(value: int) -> int:
    return (value + 3) & ~3


def _big_dir_header_size(name_len: int) -> int:
    """Word-aligned header size for a Big directory whose name is *name_len* long."""
    return _word_align(_BIG_DIR_HEADER_FIXED + name_len + 1)  # +1 for the CR terminator


def _calculate_big_dir_check(
    data: SectorsView | bytes,
    dir_size: int,
    name_len: int,
    num_entries: int,
    names_size: int,
) -> int:
    """Compute a Big directory's check byte (ROR-13 accumulation).

    The accumulated region is the header, entries and name heap; then, after
    the whole tail's leading bytes, the tail's whole words and its final bytes
    (all but the check byte itself).
    """
    header_size = _big_dir_header_size(name_len)
    end_of_check = header_size + num_entries * _BIG_DIR_ENTRY_SIZE + names_size
    tail = dir_size - _BIG_DIR_TAIL_SIZE

    dircheck = 0
    amt = 0
    while amt + 3 < end_of_check:
        dircheck = _read_32bit_le(data, amt) ^ _ror13(dircheck)
        amt += 4
    while amt < end_of_check:
        dircheck = data[amt] ^ _ror13(dircheck)
        amt += 1

    amt = tail  # Big directories do not skip the first tail byte
    while amt + 3 < dir_size - 4:
        dircheck = _read_32bit_le(data, amt) ^ _ror13(dircheck)
        amt += 4
    while amt < dir_size - 1:
        dircheck = data[amt] ^ _ror13(dircheck)
        amt += 1

    return (
        (dircheck & 0xFF)
        ^ ((dircheck >> 8) & 0xFF)
        ^ ((dircheck >> 16) & 0xFF)
        ^ ((dircheck >> 24) & 0xFF)
    )


class BigDirectoryFormat(ADFSDirectoryFormat):
    """Big ADFS directory format (E+/F+/G): variable size, name heap.

    ``size_in_bytes``/``size_in_sectors`` give the default size used when
    creating a new directory; an existing directory's true size comes from its
    ``BigDirSize`` header field via :meth:`directory_size`.
    """

    @property
    def size_in_bytes(self) -> int:
        return _BIG_DIR_DEFAULT_SIZE

    @property
    def size_in_sectors(self) -> int:
        return _BIG_DIR_DEFAULT_SIZE // 256

    @property
    def max_entries(self) -> int:
        # Effectively unbounded (limited by the directory's byte size).
        return 0x7FFFFFFF

    def directory_size(self, header: SectorsView) -> int:
        return _read_32bit_le(header, 0x0C)

    def serialized_size(self, directory: _ADFSDirectory) -> int:
        return directory.big_dir_size or _BIG_DIR_DEFAULT_SIZE

    def required_size(self, directory: _ADFSDirectory, sector_size: int) -> int:
        """Smallest block size that holds *directory*, rounded up to a sector.

        The default (2048 bytes) is the floor; a directory that outgrows its
        current block must be reallocated at this size.
        """
        name_len = len(directory.name.encode("latin-1"))
        header_size = _big_dir_header_size(name_len)
        names_size = _word_align(
            sum(len(e.name.encode("latin-1")) + 1 for e in directory.entries)
        )
        needed = (
            header_size
            + len(directory.entries) * _BIG_DIR_ENTRY_SIZE
            + names_size
            + _BIG_DIR_TAIL_SIZE
        )
        rounded = ((needed + sector_size - 1) // sector_size) * sector_size
        return max(_BIG_DIR_DEFAULT_SIZE, rounded)

    def parse(self, data: SectorsView, disc_address: int) -> _ADFSDirectory:
        start_mas_seq = data[0x00]
        start_name = bytes(data[0x04:0x08])
        if start_name != _BIG_DIR_START_NAME:
            raise ADFSDirectoryError(
                f"Invalid Big directory signature: {start_name!r} "
                f"(expected {_BIG_DIR_START_NAME!r})"
            )

        name_len = _read_32bit_le(data, 0x08)
        dir_size = _read_32bit_le(data, 0x0C)
        num_entries = _read_32bit_le(data, 0x10)
        names_size = _read_32bit_le(data, 0x14)
        parent_address = _read_32bit_le(data, 0x18)
        dir_name = _strip_name_8bit(bytes(data[0x1C : 0x1C + name_len]))

        tail = dir_size - _BIG_DIR_TAIL_SIZE
        end_name = bytes(data[tail : tail + 4])
        if end_name != _BIG_DIR_END_NAME:
            raise ADFSDirectoryError(
                f"Big directory tail signature {end_name!r} does not match {_BIG_DIR_END_NAME!r}"
            )
        end_mas_seq = data[tail + 4]
        if start_mas_seq != end_mas_seq:
            raise ADFSDirectoryError(
                f"Broken directory: StartMasSeq ({start_mas_seq}) != EndMasSeq ({end_mas_seq})"
            )
        expected_check = data[tail + 7]
        calculated_check = _calculate_big_dir_check(
            data, dir_size, name_len, num_entries, names_size
        )
        if expected_check != calculated_check:
            raise ADFSDirectoryError(
                f"Big directory check byte mismatch: stored 0x{expected_check:02X}, "
                f"calculated 0x{calculated_check:02X}"
            )

        header_size = _big_dir_header_size(name_len)
        heap_offset = header_size + num_entries * _BIG_DIR_ENTRY_SIZE

        entries = []
        for i in range(num_entries):
            offset = header_size + i * _BIG_DIR_ENTRY_SIZE
            load_address = _read_32bit_le(data, offset + 0x00)
            exec_address = _read_32bit_le(data, offset + 0x04)
            length = _read_32bit_le(data, offset + 0x08)
            indirect = _read_32bit_le(data, offset + 0x0C)
            atts = _read_32bit_le(data, offset + 0x10)
            name_length = _read_32bit_le(data, offset + 0x14)
            name_ptr = _read_32bit_le(data, offset + 0x18)
            name = _strip_name_8bit(
                bytes(data[heap_offset + name_ptr : heap_offset + name_ptr + name_length])
            )
            entries.append(
                _ADFSDirectoryEntry(
                    name=name,
                    load_address=load_address,
                    exec_address=exec_address,
                    length=length,
                    indirect_disc_address=indirect,
                    sequence_number=0,
                    attributes=_extract_new_attributes(atts),
                )
            )

        return _ADFSDirectory(
            name=dir_name,
            title="",
            parent_address=parent_address,
            disc_address=disc_address,
            entries=tuple(entries),
            sequence_number=start_mas_seq,
            signature=_BIG_DIR_START_NAME,
            big_dir_size=dir_size,
        )

    def serialize(self, directory: _ADFSDirectory, data: SectorsView) -> None:
        dir_size = directory.big_dir_size or _BIG_DIR_DEFAULT_SIZE
        if len(data) < dir_size:
            raise ADFSDirectoryError(
                f"Output data too short: {len(data)} bytes, need {dir_size}"
            )
        for i in range(dir_size):
            data[i] = 0

        dir_name = directory.name.encode("latin-1")
        name_len = len(dir_name)
        header_size = _big_dir_header_size(name_len)

        # Header.
        data[0x00] = directory.sequence_number & 0xFF
        data[0x04:0x08] = _BIG_DIR_START_NAME
        _write_32bit_le(data, 0x08, name_len)
        _write_32bit_le(data, 0x0C, dir_size)
        _write_32bit_le(data, 0x10, len(directory.entries))
        _write_32bit_le(data, 0x18, directory.parent_address)
        for i, b in enumerate(dir_name):
            data[0x1C + i] = b
        data[0x1C + name_len] = 0x0D  # CR terminator

        # Entries and name heap.
        heap_offset = header_size + len(directory.entries) * _BIG_DIR_ENTRY_SIZE
        name_ptr = 0
        for i, entry in enumerate(directory.entries):
            offset = header_size + i * _BIG_DIR_ENTRY_SIZE
            _write_32bit_le(data, offset + 0x00, entry.load_address)
            _write_32bit_le(data, offset + 0x04, entry.exec_address)
            _write_32bit_le(data, offset + 0x08, entry.length)
            _write_32bit_le(data, offset + 0x0C, entry.indirect_disc_address)
            _write_32bit_le(data, offset + 0x10, _new_attributes_byte(entry.attributes))
            name_bytes = entry.name.encode("latin-1")
            _write_32bit_le(data, offset + 0x14, len(name_bytes))
            _write_32bit_le(data, offset + 0x18, name_ptr)
            for j, b in enumerate(name_bytes):
                data[heap_offset + name_ptr + j] = b
            data[heap_offset + name_ptr + len(name_bytes)] = 0x0D  # CR terminator
            name_ptr += len(name_bytes) + 1

        names_size = _word_align(name_ptr)
        _write_32bit_le(data, 0x14, names_size)

        # Tail.
        tail = dir_size - _BIG_DIR_TAIL_SIZE
        data[tail : tail + 4] = _BIG_DIR_END_NAME
        data[tail + 4] = directory.sequence_number & 0xFF
        data[tail + 7] = _calculate_big_dir_check(
            data, dir_size, name_len, len(directory.entries), names_size
        )


def _write_32bit_le(data: SectorsView, offset: int, value: int) -> None:
    for i in range(4):
        data[offset + i] = (value >> (8 * i)) & 0xFF

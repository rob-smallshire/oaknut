"""ADFS New Map (FileCore zoned allocation) — internal module.

The New Map replaces the Old free-space map on the RISC OS shapes (E/F and
their ``+`` variants, and new-map hard discs). Its structure, per zone, is:

    zone header (4 bytes)   Zone_Check, FreeLink (2), CrossCheck
    disc record (60 bytes)  zone 0 only, at offset 0x04
    allocation bitmap       a bitstream of fragments

Every file object (file or directory) is one or more *fragments*. A fragment
is a run in the bitstream: ``idlen`` bits of fragment ID (LSB first), then a
number of zero bits, then a single set *stop* bit. The number of map bits from
the start of the ID up to and including the stop bit, times ``bytes_per_map_bit``,
is the fragment's length on disc; the bit distance of the ID from the start of
the map, times ``bytes_per_map_bit``, is its disc address.

A directory entry's three-byte "indirect disc address" is not a sector: it is a
fragment ID in the high bits and a within-fragment sector offset in the low
byte. Resolving it needs the map — that indirection is what this module adds.

This rung supports single-zone maps (the E format). Multi-zone maps (F and
hard discs) layer the zone search order on top and are added later.

References: Gerald Holdsworth, *Guide to Disc Formats* (New Map chapter);
FileCore, RISC OS PRM vol. 2.
"""

from __future__ import annotations

from dataclasses import dataclass

from oaknut.adfs.exceptions import ADFSMapError, ADFSValidationError
from oaknut.discimage.sectors_view import SectorsView

# Byte offsets within a zone's leading structures.
_ZONE_CHECK_OFFSET = 0x00
_ZONE_FREELINK_OFFSET = 0x01  # 2 bytes
_ZONE_CROSSCHECK_OFFSET = 0x03
_ZONE_HEADER_SIZE = 4
_DISC_RECORD_OFFSET = 0x04  # zone 0 only
_DISC_RECORD_SIZE = 60
# Zone 0's map bits begin after the zone header and (in zone 0) the disc record.
_ZONE0_MAP_START = _ZONE_HEADER_SIZE + _DISC_RECORD_SIZE  # 0x40


def _read_le(data: SectorsView | bytes, offset: int, length: int) -> int:
    value = 0
    for i in range(length):
        value |= data[offset + i] << (8 * i)
    return value


def _write_le(data: SectorsView, offset: int, value: int, length: int) -> None:
    for i in range(length):
        data[offset + i] = (value >> (8 * i)) & 0xFF


def write_bits(data: SectorsView, bit_position: int, num_bits: int, value: int) -> None:
    """Write *num_bits* of *value* (LSB first) at an absolute bit position."""
    for i in range(num_bits):
        byte_index = (bit_position + i) >> 3
        bit_index = (bit_position + i) & 7
        if (value >> i) & 1:
            data[byte_index] |= 1 << bit_index
        else:
            data[byte_index] &= ~(1 << bit_index) & 0xFF


@dataclass(frozen=True)
class DiscRecord:
    """A parsed 60-byte FileCore disc record (zone 0).

    Only the fields needed for New Map addressing and disc-level metadata
    are surfaced. The ``+`` extension fields (disc_size2, big_flag,
    format_version, root_size…) are ignored at this rung.
    """

    log2_sector_size: int
    sectors_per_track: int
    heads: int
    density: int
    idlen: int
    log2_bytes_per_map_bit: int
    skew: int
    boot_option: int
    low_sector: int
    nzones: int
    zone_spare: int
    root: int
    disc_size: int
    disc_id: int
    disc_name: str
    disc_type: int

    @property
    def sector_size(self) -> int:
        return 1 << self.log2_sector_size

    @property
    def bytes_per_map_bit(self) -> int:
        return 1 << self.log2_bytes_per_map_bit

    @property
    def sides_are_sequenced(self) -> bool:
        """Bit 6 of ``low_sector``: sides sequenced rather than interleaved."""
        return bool(self.low_sector & 0x40)

    def serialise(self, data: SectorsView, offset: int = _DISC_RECORD_OFFSET) -> None:
        """Write this 60-byte disc record into *data* at *offset* (0x04)."""
        data[offset + 0x00] = self.log2_sector_size
        data[offset + 0x01] = self.sectors_per_track
        data[offset + 0x02] = self.heads
        data[offset + 0x03] = self.density
        data[offset + 0x04] = self.idlen
        data[offset + 0x05] = self.log2_bytes_per_map_bit
        data[offset + 0x06] = self.skew
        data[offset + 0x07] = self.boot_option
        data[offset + 0x08] = self.low_sector
        data[offset + 0x09] = self.nzones
        _write_le(data, offset + 0x0A, self.zone_spare, 2)
        _write_le(data, offset + 0x0C, self.root, 4)
        _write_le(data, offset + 0x10, self.disc_size, 4)
        _write_le(data, offset + 0x14, self.disc_id, 2)
        name = self.disc_name.encode("latin-1")[:10].ljust(10, b"\x00")
        for i in range(10):
            data[offset + 0x16 + i] = name[i]
        _write_le(data, offset + 0x20, self.disc_type, 4)

    @classmethod
    def parse(cls, data: SectorsView | bytes, offset: int = _DISC_RECORD_OFFSET) -> DiscRecord:
        """Parse a disc record starting at *offset* (0x04 within zone 0)."""
        disc_name = bytes(data[offset + 0x16 : offset + 0x20]).rstrip(b"\x00 ").decode(
            "latin-1"
        )
        return cls(
            log2_sector_size=data[offset + 0x00],
            sectors_per_track=data[offset + 0x01],
            heads=data[offset + 0x02],
            density=data[offset + 0x03],
            idlen=data[offset + 0x04],
            log2_bytes_per_map_bit=data[offset + 0x05],
            skew=data[offset + 0x06],
            boot_option=data[offset + 0x07],
            low_sector=data[offset + 0x08],
            nzones=data[offset + 0x09],
            zone_spare=_read_le(data, offset + 0x0A, 2),
            root=_read_le(data, offset + 0x0C, 4),
            disc_size=_read_le(data, offset + 0x10, 4),
            disc_id=_read_le(data, offset + 0x14, 2),
            disc_name=disc_name,
            disc_type=_read_le(data, offset + 0x20, 4),
        )

    def looks_valid(self) -> bool:
        """Cheap plausibility gate used during format detection.

        Mirrors the guide's New Map identification: ``idlen`` under 22,
        at least one zone, a sector size in the supported 8..12 range,
        and ``idlen`` at least ``log2secsize + 3``.
        """
        if not (8 <= self.log2_sector_size <= 12):
            return False
        if self.nzones < 1:
            return False
        if not (self.log2_sector_size + 3 <= self.idlen < 22):
            return False
        return True


def calculate_zone_check(map_bytes: SectorsView | bytes, zone: int, log2_sector_size: int) -> int:
    """Compute a zone's ``Zone_Check`` byte (FileCore ``map_zone_valid_byte``).

    A 32-bit add-with-carry runs over the zone's words from four bytes off the
    end down to the second word; the first word (which contains the check byte)
    is folded in last with the check byte substituted by zero. The four bytes of
    the resulting word are XOR-ed together.
    """
    zone_start = zone << log2_sector_size
    sv0 = sv1 = sv2 = sv3 = 0
    rover = ((zone + 1) << log2_sector_size) - 4
    while rover > zone_start:
        sv0 = (sv0 + map_bytes[rover + 0] + (sv3 >> 8)) & 0xFFFFFFFF
        sv3 &= 0xFF
        sv1 = (sv1 + map_bytes[rover + 1] + (sv0 >> 8)) & 0xFFFFFFFF
        sv0 &= 0xFF
        sv2 = (sv2 + map_bytes[rover + 2] + (sv1 >> 8)) & 0xFFFFFFFF
        sv1 &= 0xFF
        sv3 = (sv3 + map_bytes[rover + 3] + (sv2 >> 8)) & 0xFFFFFFFF
        sv2 &= 0xFF
        rover -= 4
    # First word: substitute the check byte (byte 0) with zero.
    sv0 = (sv0 + (sv3 >> 8)) & 0xFFFFFFFF
    sv1 = (sv1 + map_bytes[rover + 1] + (sv0 >> 8)) & 0xFFFFFFFF
    sv2 = (sv2 + map_bytes[rover + 2] + (sv1 >> 8)) & 0xFFFFFFFF
    sv3 = (sv3 + map_bytes[rover + 3] + (sv2 >> 8)) & 0xFFFFFFFF
    return (sv0 ^ sv1 ^ sv2 ^ sv3) & 0xFF


class NewMap:
    """A single-zone New Map: fragment index plus disc-level metadata.

    Constructed over a byte reader so it is independent of surface layout;
    the caller supplies the disc record (already parsed from zone 0) and a
    callable returning ``length`` bytes at a linear disc address.
    """

    def __init__(
        self,
        map_bytes: SectorsView,
        disc_record: DiscRecord,
        read_bytes,
    ):
        if disc_record.nzones != 1:
            raise ADFSMapError(
                f"multi-zone New Map (nzones={disc_record.nzones}) is not yet supported"
            )
        self._map = map_bytes
        self._dr = disc_record
        self._read_bytes = read_bytes
        # fragment id -> list of (disc_address_bytes, capacity_bytes) in scan order
        self._fragments: dict[int, list[tuple[int, int]]] = {}
        self._free_bytes = 0
        self._build_index()

    @property
    def disc_record(self) -> DiscRecord:
        return self._dr

    def _bit(self, bit_pos: int) -> int:
        return (self._map[bit_pos >> 3] >> (bit_pos & 7)) & 1

    def _build_index(self) -> None:
        dr = self._dr
        idlen = dr.idlen
        bpmb = dr.bytes_per_map_bit
        map_start_bit = _ZONE0_MAP_START * 8
        usable_bits = dr.disc_size // bpmb

        pos = 0
        while pos < usable_bits:
            base = map_start_bit + pos
            frag_id = 0
            for i in range(idlen):
                frag_id |= self._bit(base + i) << i
            # Length: idlen bits, then zeros, then a set stop bit (inclusive).
            length_bits = idlen
            j = idlen
            while pos + length_bits < usable_bits:
                stop = self._bit(base + j)
                length_bits += 1
                j += 1
                if stop:
                    break
            length_bytes = length_bits * bpmb
            if frag_id == 0:
                self._free_bytes += length_bytes
            else:
                self._fragments.setdefault(frag_id, []).append((pos * bpmb, length_bytes))
            pos += length_bits

    @staticmethod
    def _split_indirect(indirect: int) -> tuple[int, int]:
        """Split a three-byte indirect address into (fragment_id, sector_offset)."""
        return indirect >> 8, indirect & 0xFF

    def _within_offset(self, sector_offset: int) -> int:
        # The low byte is a 1-based sector index into the fragment; 0 means the
        # fragment start. Both 0 and 1 therefore denote offset zero.
        if sector_offset == 0:
            return 0
        return (sector_offset - 1) * self._dr.sector_size

    def object_start(self, indirect: int) -> int:
        """Return the linear disc byte address an object begins at."""
        frag_id, sector_offset = self._split_indirect(indirect)
        fragments = self._fragments.get(frag_id)
        if not fragments:
            raise ADFSMapError(
                f"No allocated fragment for id 0x{frag_id:X} (indirect 0x{indirect:X})"
            )
        return fragments[0][0] + self._within_offset(sector_offset)

    def read_object(self, indirect: int, length: int) -> bytes:
        """Read *length* bytes of an object, following its fragment chain."""
        frag_id, sector_offset = self._split_indirect(indirect)
        fragments = self._fragments.get(frag_id)
        if not fragments:
            raise ADFSMapError(
                f"No allocated fragment for id 0x{frag_id:X} (indirect 0x{indirect:X})"
            )
        skip = self._within_offset(sector_offset)
        out = bytearray()
        remaining = length
        for disc_address, capacity in fragments:
            if skip >= capacity:
                skip -= capacity
                continue
            available = capacity - skip
            take = min(available, remaining)
            out += self._read_bytes(disc_address + skip, take)
            skip = 0
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 0:
            raise ADFSMapError(
                f"Object 0x{indirect:X} is shorter on disc ({length - remaining} bytes) "
                f"than its catalogued length ({length} bytes)"
            )
        return bytes(out)

    # --- Disc-level metadata ---

    @property
    def total_size(self) -> int:
        return self._dr.disc_size

    @property
    def free_space(self) -> int:
        return self._free_bytes

    @property
    def boot_option(self) -> int:
        return self._dr.boot_option

    @property
    def disc_name(self) -> str:
        return self._dr.disc_name

    def validate(self) -> list[ADFSValidationError]:
        """Validate the zone-0 check byte."""
        errors: list[ADFSValidationError] = []
        expected = self._map[_ZONE_CHECK_OFFSET]
        calculated = calculate_zone_check(self._map, 0, self._dr.log2_sector_size)
        if expected != calculated:
            errors.append(
                ADFSValidationError(
                    f"Zone 0 check byte mismatch: stored 0x{expected:02X}, "
                    f"calculated 0x{calculated:02X}"
                )
            )
        return errors


# --- Blank New Map creation ---

#: FileCore ``disctype`` word for the non-``+`` shapes (D/E/F).
_DISCTYPE_NON_PLUS = 0x20158C78

#: Spare (non-allocation) map bits per zone for the 800K E format.
_E_ZONE_SPARE = 1312


def e_disc_record(title: str, *, disc_id: int = 0, boot_option: int = 0) -> DiscRecord:
    """Build the disc record for a blank 800K single-zone ADFS E disc."""
    return DiscRecord(
        log2_sector_size=10,
        sectors_per_track=5,
        heads=2,
        density=2,
        idlen=15,
        log2_bytes_per_map_bit=7,
        skew=1,
        boot_option=boot_option,
        low_sector=0,
        nzones=1,
        zone_spare=_E_ZONE_SPARE,
        root=0x203,
        disc_size=819200,
        disc_id=disc_id,
        disc_name=title[:10],
        disc_type=_DISCTYPE_NON_PLUS,
    )


def format_blank_single_zone(data: SectorsView, disc_record: DiscRecord, root_size: int) -> int:
    """Lay down a blank single-zone New Map; return the root's disc byte address.

    Writes, into *data* (the whole image), the zone header, disc record,
    allocation bitmap and its duplicate copy. The bitmap holds one system
    fragment (id 2) covering the two map copies plus the root, with the rest
    free. The caller writes the empty root directory at the returned address.
    """
    if disc_record.nzones != 1:
        raise ADFSMapError("format_blank_single_zone only supports single-zone maps")
    secsize = disc_record.sector_size
    bpmb = disc_record.bytes_per_map_bit
    idlen = disc_record.idlen
    map_start_bit = _ZONE0_MAP_START * 8  # 512 — the disc address origin

    # System fragment (id 2): the two map copies (secsize*2) plus the root.
    system_bits = (secsize * 2 + root_size) // bpmb
    write_bits(data, map_start_bit, idlen, 2)
    write_bits(data, map_start_bit + system_bits - 1, 1, 1)  # fragment stop bit

    # Terminate the free region at the last usable map bit.
    eod_bit = disc_record.disc_size // bpmb
    write_bits(data, map_start_bit + eod_bit - 1, 1, 1)

    # FreeLink: 15-bit distance from the link (bit 8) to the sole free area,
    # with the terminator flag (0x8000) set.
    free_start_bit = map_start_bit + system_bits
    _write_le(data, _ZONE_FREELINK_OFFSET, 0x8000 | (free_start_bit - 8), 2)
    data[_ZONE_CROSSCHECK_OFFSET] = 0xFF

    disc_record.serialise(data)

    # Zone check over the finished zone, then duplicate the whole map.
    data[_ZONE_CHECK_OFFSET] = calculate_zone_check(data, 0, disc_record.log2_sector_size)
    for i in range(secsize):
        data[secsize + i] = data[i]

    return secsize * 2  # root disc byte address

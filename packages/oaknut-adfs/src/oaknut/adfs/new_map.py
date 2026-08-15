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

from dataclasses import dataclass, replace

from oaknut.adfs.exceptions import ADFSDiscFullError, ADFSMapError, ADFSValidationError
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
    #: ``+`` extension: 1 on E+/F+/G discs, which use Big directories; 0 otherwise.
    format_version: int = 0
    #: ``+`` extension: byte size of the root directory (Big directories vary).
    root_size: int = 0

    @property
    def uses_big_directories(self) -> bool:
        """Whether this disc uses Big directories (the ``+`` formats)."""
        return self.format_version >= 1

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
        if self.format_version:
            _write_le(data, offset + 0x2C, self.format_version, 4)
            _write_le(data, offset + 0x30, self.root_size, 4)

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
            format_version=_read_le(data, offset + 0x2C, 4),
            root_size=_read_le(data, offset + 0x30, 4),
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


def compute_bootmap(disc_record: DiscRecord) -> int:
    """The disc offset of the allocation map (0 single-zone, mid-disc multi-zone).

    FileCore places a multi-zone map in the middle of the disc. The formula
    (from DiscImageManager) subtracts the disc record's 480 bits for discs of
    more than two zones.
    """
    if disc_record.nzones <= 1:
        return 0
    secsize = disc_record.sector_size
    zz = _DISC_RECORD_SIZE * 8 if disc_record.nzones > 2 else 0
    zone_bits = 8 * secsize - disc_record.zone_spare
    return ((disc_record.nzones // 2) * zone_bits - zz) * disc_record.bytes_per_map_bit


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
        write_bytes=None,
        base_offset: int = 0,
    ):
        # ``map_bytes`` starts at ``bootmap`` — the map's disc offset, which is
        # zero for the single-zone (E) format and mid-disc for multi-zone (F).
        self._map = map_bytes
        self._dr = disc_record
        self._read_bytes = read_bytes
        self._write_bytes = write_bytes
        # Emulator-header shift: physical image offset = (disc addr + base) mod size.
        self._base_offset = base_offset
        self._bootmap = compute_bootmap(disc_record)
        # fragment id -> list of (logical_disc_address, capacity_bytes) in scan order
        self._fragments: dict[int, list[tuple[int, int]]] = {}
        self._free_bytes = 0
        self._build_index()

    @property
    def _multizone(self) -> bool:
        return self._dr.nzones > 1

    def physical_offset(self, disc_address: int) -> int:
        """Translate a disc address to its physical image offset (emulator shift)."""
        return (disc_address + self._base_offset) % self._dr.disc_size

    def _root_physical(self) -> int:
        """Physical disc offset of the root directory.

        The root is special-cased (as in FileCore): it always sits just past
        the two map copies, at ``bootmap + nzones*secsize*2``. Its fragment id
        (2) is shared with the system area, so it cannot be resolved through the
        ordinary bitmap scan.
        """
        return self._bootmap + self._dr.nzones * self._dr.sector_size * 2

    @property
    def disc_record(self) -> DiscRecord:
        return self._dr

    @property
    def _map_start_bit(self) -> int:
        return _ZONE0_MAP_START * 8

    @property
    def _usable_bits(self) -> int:
        """Number of allocation-map bits the disc occupies (single zone)."""
        return self._dr.disc_size // self._dr.bytes_per_map_bit

    def _bit(self, bit_pos: int) -> int:
        return (self._map[bit_pos >> 3] >> (bit_pos & 7)) & 1

    def _read_bits(self, bit_pos: int, num_bits: int) -> int:
        value = 0
        for i in range(num_bits):
            value |= self._bit(bit_pos + i) << i
        return value

    def _cell_length_bits(self, pos: int) -> int:
        """Length of the map cell starting at *pos* (idlen field + zeros + stop)."""
        idlen = self._dr.idlen
        base = self._map_start_bit + pos
        length_bits = idlen
        j = idlen
        while pos + length_bits < self._usable_bits:
            stop = self._bit(base + j)
            length_bits += 1
            j += 1
            if stop:
                break
        return length_bits

    def _free_area_positions(self) -> set[int]:
        """Positions (map-bit offsets) of free areas, walked via the FreeLink chain.

        Free areas cannot be told apart from allocated fragments by their
        leading bits — those bits are the link to the next free area, not a
        zero id — so the chain is the authoritative source. The header link
        (byte 1) has its top bit set as a marker; a link value of zero ends
        the chain.
        """
        positions: set[int] = set()
        header = self._read_bits(8, 16) & 0x7FFF
        if header == 0:
            return positions
        freeptr = 8 + header
        guard = 0
        limit = self._usable_bits + 1
        while guard <= limit:
            positions.add(freeptr - self._map_start_bit)
            link = self._read_bits(freeptr, self._dr.idlen)
            if link == 0:
                break
            freeptr += link
            guard += 1
        return positions

    def _build_index(self) -> None:
        self._fragments = {}
        self._free_bytes = 0
        if self._multizone:
            for zone in range(self._dr.nzones):
                self._index_zone(zone)
            return

        bpmb = self._dr.bytes_per_map_bit
        free_positions = self._free_area_positions()

        pos = 0
        while pos < self._usable_bits:
            length_bits = self._cell_length_bits(pos)
            length_bytes = length_bits * bpmb
            if pos in free_positions:
                self._free_bytes += length_bytes
            else:
                frag_id = self._read_bits(self._map_start_bit + pos, self._dr.idlen)
                self._fragments.setdefault(frag_id, []).append((pos * bpmb, length_bytes, 0))
            pos += length_bits

    def _ordered_fragments(self, frag_id: int) -> "list[tuple[int, int, int]] | None":
        """An object's fragments as ``(disc_address, capacity, zone)``, in file order.

        Within a zone the scan already yields disc-address order. Across zones,
        FileCore joins fragments in the search order that starts at the id's
        home zone and wraps, so multi-fragment objects spanning zones read back
        in the right order.
        """
        fragments = self._fragments.get(frag_id)
        if not fragments or not self._multizone or len(fragments) == 1:
            return fragments
        start_zone = frag_id // self._id_per_zone()
        nzones = self._dr.nzones
        return sorted(fragments, key=lambda f: (f[2] - start_zone) % nzones)

    # --- Multi-zone reading (F format) ---
    #
    # The map lives at ``bootmap`` (mid-disc) as ``nzones`` zones, each a
    # sector with its own header; zone 0 also carries the disc record. All map
    # coordinates below are absolute bits from ``bootmap`` (``self._map`` bit 0).
    # Ported from DiscImageManager's BuildADFSBitmapIndex.

    def _zone_bit_span(self, zone: int) -> tuple[int, int]:
        """(start, end) map-bit positions of *zone*'s allocation area."""
        secsize = self._dr.sector_size
        start = zone * secsize * 8 + (_ZONE0_MAP_START * 8 if zone == 0 else _ZONE_HEADER_SIZE * 8)
        end = (zone + 1) * secsize * 8
        return start, end

    def _free_positions_in_zone(self, zone: int) -> set[int]:
        """Cell-start bit positions of free areas in *zone*, via its FreeLink chain."""
        positions: set[int] = set()
        secsize = self._dr.sector_size
        header_bit = (zone * secsize + _ZONE_FREELINK_OFFSET) * 8
        header = self._read_bits(header_bit, 16) & 0x7FFF
        if header == 0:
            return positions
        _, end = self._zone_bit_span(zone)
        freeptr = header_bit + header  # the free area is `header` bits past the link field
        guard = 0
        while guard <= secsize * 8:
            positions.add(freeptr)
            link = self._read_bits(freeptr, self._dr.idlen)
            if link == 0 or freeptr >= end:
                break
            freeptr += link
            guard += 1
        return positions

    def _index_zone(self, zone: int) -> None:
        dr = self._dr
        idlen = dr.idlen
        bpmb = dr.bytes_per_map_bit
        start, end = self._zone_bit_span(zone)
        free_positions = self._free_positions_in_zone(zone)

        b = start
        while b < end:
            # Cell = idlen-bit field, then zeros, then a set stop bit (inclusive).
            j = b + idlen
            while j < end and not self._bit(j):
                j += 1
            length_bits = (j - b) + 1
            length_bytes = length_bits * bpmb
            if b in free_positions:
                self._free_bytes += length_bytes
            else:
                frag_id = self._read_bits(b, idlen)
                if frag_id > 0:
                    off = b - _ZONE0_MAP_START * 8  # the "id offset" DIM subtracts from
                    disc_address = ((off - dr.zone_spare * zone) * bpmb) % dr.disc_size
                    self._fragments.setdefault(frag_id, []).append(
                        (disc_address, length_bytes, zone)
                    )
            b = j + 1

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

    def _read_physical(self, physical: int, length: int) -> bytes:
        """Read *length* bytes from a physical offset, wrapping at the disc size."""
        disc_size = self._dr.disc_size
        if physical + length <= disc_size:
            return self._read_bytes(physical, length)
        first = disc_size - physical
        return self._read_bytes(physical, first) + self._read_bytes(0, length - first)

    def _is_system_root(self, indirect: int) -> bool:
        """Whether *indirect* is a New-directory root packed in system fragment 2.

        Such a root cannot be resolved through the ordinary bitmap scan (its id
        is shared with the multi-part system fragment), so it is special-cased.
        A Big-directory root is its own fragment and resolves normally, which is
        also what lets it move when it grows.
        """
        return indirect == self._dr.root and (indirect >> 8) == 2

    def object_start(self, indirect: int) -> int:
        """Return the physical disc byte address an object begins at."""
        if self._is_system_root(indirect):
            return self._root_physical()
        frag_id, sector_offset = self._split_indirect(indirect)
        fragments = self._ordered_fragments(frag_id)
        if not fragments:
            raise ADFSMapError(
                f"No allocated fragment for id 0x{frag_id:X} (indirect 0x{indirect:X})"
            )
        # A fragment's disc address is already a physical image offset.
        return fragments[0][0] + self._within_offset(sector_offset)

    def read_object(self, indirect: int, length: int) -> bytes:
        """Read *length* bytes of an object, following its fragment chain."""
        if self._is_system_root(indirect):
            return self._read_physical(self._root_physical(), length)
        frag_id, sector_offset = self._split_indirect(indirect)
        fragments = self._ordered_fragments(frag_id)
        if not fragments:
            raise ADFSMapError(
                f"No allocated fragment for id 0x{frag_id:X} (indirect 0x{indirect:X})"
            )
        skip = self._within_offset(sector_offset)
        out = bytearray()
        remaining = length
        for physical_address, capacity, _zone in fragments:
            if skip >= capacity:
                skip -= capacity
                continue
            available = capacity - skip
            take = min(available, remaining)
            out += self._read_physical(physical_address + skip, take)
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

    # --- Mutation ---
    #
    # Writes work by parsing the zone bitstream into a list of cells (each an
    # allocated fragment or a free area), editing the list, then rewriting the
    # whole bitstream and rebuilding the FreeLink chain. This is easier to keep
    # correct than in-place bit surgery and produces the same valid structures.
    # Allocation is single-fragment: it places an object in one contiguous free
    # area. That always succeeds on a fresh disc (one big free area); a disc
    # fragmented by deletions could refuse a large object even with enough total
    # free space. Multi-fragment allocation is a later refinement.

    def _parse_cells(self) -> list[list]:
        """Tile the usable map into ``[fragment_id_or_None, length_bits]`` cells."""
        free_positions = self._free_area_positions()
        cells: list[list] = []
        pos = 0
        while pos < self._usable_bits:
            length_bits = self._cell_length_bits(pos)
            if pos in free_positions:
                cells.append([None, length_bits])
            else:
                fid = self._read_bits(self._map_start_bit + pos, self._dr.idlen)
                cells.append([fid, length_bits])
            pos += length_bits
        return cells

    def _rewrite_cells(self, cells: list[list]) -> None:
        """Rewrite the bitstream, FreeLink chain, zone check and map copy."""
        idlen = self._dr.idlen
        map_start = self._map_start_bit

        end_byte = (map_start + self._usable_bits + 7) // 8
        for b in range(_ZONE0_MAP_START, end_byte):
            self._map[b] = 0

        pos = 0
        free_positions: list[int] = []
        for fid, length_bits in cells:
            base = map_start + pos
            if fid is not None:
                write_bits(self._map, base, idlen, fid)
            else:
                free_positions.append(pos)
            write_bits(self._map, base + length_bits - 1, 1, 1)  # stop bit
            pos += length_bits

        self._write_free_chain(free_positions)
        self._finalise_zone()
        self._build_index()

    def _write_free_chain(self, free_positions: list[int]) -> None:
        """Rebuild the FreeLink chain over the free areas (ascending order)."""
        idlen = self._dr.idlen
        map_start = self._map_start_bit
        if not free_positions:
            _write_le(self._map, _ZONE_FREELINK_OFFSET, 0x8000, 2)
            return
        prev_ptr = 8  # the header FreeLink field, at byte 1
        for i, pos in enumerate(free_positions):
            target = map_start + pos
            distance = target - prev_ptr
            if i == 0:
                # Header link: 16-bit, with the top-bit marker set.
                _write_le(self._map, _ZONE_FREELINK_OFFSET, 0x8000 | distance, 2)
            else:
                write_bits(self._map, prev_ptr, idlen, distance)
            prev_ptr = target
        # The final free area's link stays zero (already cleared) — chain end.

    def _finalise_zone(self) -> None:
        """Recompute the zone-0 check byte and duplicate the map."""
        secsize = self._dr.sector_size
        self._map[_ZONE_CHECK_OFFSET] = calculate_zone_check(
            self._map, 0, self._dr.log2_sector_size
        )
        for i in range(secsize):
            self._map[secsize + i] = self._map[i]

    def _next_fragment_id(self, cells: list[list]) -> int:
        used = {0, 1} | {fid for fid, _ in cells if fid is not None}
        candidate = 2
        while candidate in used:
            candidate += 1
        if candidate >= (1 << self._dr.idlen):
            raise ADFSDiscFullError("no free fragment id available")
        return candidate

    def allocate_object(self, length_bytes: int) -> int:
        """Allocate a single-fragment object; return its indirect disc address.

        The returned indirect address has sector offset 0 (the object owns its
        fragment). The object's data is not written — use
        :meth:`write_object_data`, or resolve the address via
        :meth:`object_start` and write through the directory layer.
        """
        if self._multizone:
            return self._allocate_multizone(length_bytes)
        need_bits = self._need_bits(length_bytes)
        cells = self._parse_cells()
        if sum(ln for fid, ln in cells if fid is None) < need_bits:
            raise ADFSDiscFullError(f"not enough free space for {length_bytes} bytes")
        new_fid = self._next_fragment_id(cells)
        self._rewrite_cells(self._fill_free_cells(cells, new_fid, need_bits))
        return new_fid << 8

    def _need_bits(self, length_bytes: int) -> int:
        """Map bits an object of *length_bytes* needs, rounded to a whole sector.

        Rounding to a sector keeps every fragment sector-aligned, so directories
        (which must sit on a sector boundary) stay aligned no matter what has
        been allocated before them.
        """
        bpmb = self._dr.bytes_per_map_bit
        align_bits = self._dr.sector_size // bpmb
        need = max(-(-length_bytes // bpmb), self._dr.idlen + 1)
        return -(-need // align_bits) * align_bits

    def _fill_free_cells(self, cells: list[list], frag_id: int, need_bits: int) -> list[list]:
        """Assign *frag_id* to enough leading free cells to cover *need_bits*.

        Free cells are taken in disc order; the last one is split if it
        overshoots. Every consumed span is a whole number of sectors, so each
        resulting fragment is a valid, sector-aligned fragment. Produces a
        multi-fragment object when no single free area is large enough.
        """
        idlen = self._dr.idlen
        remaining = need_bits
        result: list[list] = []
        for fid, length_bits in cells:
            if fid is not None or remaining <= 0:
                result.append([fid, length_bits])
                continue
            if length_bits <= remaining:
                result.append([frag_id, length_bits])
                remaining -= length_bits
            else:
                take = remaining
                leftover = length_bits - take
                if 0 < leftover < idlen + 1:
                    take, leftover = length_bits, 0
                result.append([frag_id, take])
                if leftover > 0:
                    result.append([None, leftover])
                remaining = 0
        return result

    def grow_fragment(self, indirect: int, new_size_bytes: int) -> None:
        """Extend a single-fragment object in place into the following free area.

        Used to grow the root Big directory, whose location is fixed. Raises if
        the object has more than one fragment or the following area is not free
        and large enough.
        """
        frag_id = indirect >> 8
        new_bits = new_size_bytes // self._dr.bytes_per_map_bit
        idlen = self._dr.idlen

        if self._multizone:
            for zone in range(self._dr.nzones):
                cells = self._parse_zone_cells(zone)
                if any(fid == frag_id for fid, _ in cells):
                    self._grow_in_cells(cells, frag_id, new_bits, idlen)
                    self._rewrite_zone(zone, cells)
                    return
            raise ADFSMapError(f"No allocated fragment for id 0x{frag_id:X}")

        cells = self._parse_cells()
        self._grow_in_cells(cells, frag_id, new_bits, idlen)
        self._rewrite_cells(cells)

    @staticmethod
    def _grow_in_cells(cells: list[list], frag_id: int, new_bits: int, idlen: int) -> None:
        indices = [i for i, (fid, _) in enumerate(cells) if fid == frag_id]
        if len(indices) != 1:
            raise ADFSMapError(f"cannot grow fragment id 0x{frag_id:X}: not a single fragment")
        idx = indices[0]
        current_bits = cells[idx][1]
        if current_bits >= new_bits:
            return
        grow_by = new_bits - current_bits
        following = idx + 1
        if (
            following >= len(cells)
            or cells[following][0] is not None
            or cells[following][1] < grow_by
        ):
            raise ADFSDiscFullError("no free space to grow the directory in place")
        cells[idx][1] = new_bits
        remainder = cells[following][1] - grow_by
        if remainder == 0 or remainder < idlen + 1:
            cells[idx][1] += remainder  # absorb an unusable remainder
            del cells[following]
        else:
            cells[following][1] = remainder

    def free_object(self, indirect: int) -> None:
        """Free every fragment of an object and merge adjacent free areas."""
        if self._multizone:
            return self._free_multizone(indirect)
        frag_id = indirect >> 8
        cells = self._parse_cells()
        if not any(fid == frag_id for fid, _ in cells):
            raise ADFSMapError(f"No allocated fragment for id 0x{frag_id:X}")
        for cell in cells:
            if cell[0] == frag_id:
                cell[0] = None

        merged: list[list] = []
        for fid, length_bits in cells:
            if fid is None and merged and merged[-1][0] is None:
                merged[-1][1] += length_bits
            else:
                merged.append([fid, length_bits])
        self._rewrite_cells(merged)

    def write_object_data(self, indirect: int, data: bytes) -> None:
        """Write *data* across an object's fragments."""
        if self._write_bytes is None:
            raise ADFSMapError("this New Map was opened read-only")
        frag_id, sector_offset = self._split_indirect(indirect)
        fragments = self._ordered_fragments(frag_id)
        if not fragments:
            raise ADFSMapError(f"No allocated fragment for id 0x{frag_id:X}")
        skip = self._within_offset(sector_offset)
        offset = 0
        remaining = len(data)
        for physical_address, capacity, _zone in fragments:
            if skip >= capacity:
                skip -= capacity
                continue
            available = capacity - skip
            take = min(available, remaining)
            self._write_bytes(physical_address + skip, data[offset : offset + take])
            skip = 0
            offset += take
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 0:
            raise ADFSMapError(
                f"Object 0x{indirect:X} fragments hold too little for {len(data)} bytes"
            )

    # --- Multi-zone writing (F format) ---
    #
    # Each zone is allocated independently: a new object goes in a zone that has
    # room, taking a fragment id from that zone's id range so RISC OS's
    # zone-from-id search lands on it. Only the chosen zone's bitstream,
    # FreeLink chain, check byte and map copy are rewritten. Single-fragment,
    # like the single-zone allocator.

    def _zone_usable_end(self, zone: int) -> int:
        """One past the last allocation bit of *zone* (the free terminator)."""
        secsize = self._dr.sector_size
        terminator = _ZONE_HEADER_SIZE * 8 + (secsize * 8 - self._dr.zone_spare - 1)
        return zone * secsize * 8 + terminator + 1

    def _parse_zone_cells(self, zone: int) -> list[list]:
        """Tile *zone*'s allocation area into ``[fragment_id_or_None, len]`` cells."""
        idlen = self._dr.idlen
        free_positions = self._free_positions_in_zone(zone)
        cells: list[list] = []
        b = self._zone_bit_span(zone)[0]
        end = self._zone_usable_end(zone)
        while b < end:
            j = b + idlen
            while j < end and not self._bit(j):
                j += 1
            length_bits = (j - b) + 1
            if b in free_positions:
                cells.append([None, length_bits])
            else:
                cells.append([self._read_bits(b, idlen), length_bits])
            b = j + 1
        return cells

    def _write_zone_free_chain(self, zone: int, free_positions: list[int]) -> None:
        secsize = self._dr.sector_size
        idlen = self._dr.idlen
        link_offset = zone * secsize + _ZONE_FREELINK_OFFSET
        if not free_positions:
            _write_le(self._map, link_offset, 0x8000, 2)
            return
        header_bit = (zone * secsize + _ZONE_FREELINK_OFFSET) * 8
        prev = header_bit
        for i, pos in enumerate(free_positions):
            distance = pos - prev
            if i == 0:
                _write_le(self._map, link_offset, 0x8000 | distance, 2)
            else:
                write_bits(self._map, prev, idlen, distance)
            prev = pos
        # The last free area's link stays zero (cleared) — chain end.

    def _rewrite_zone(self, zone: int, cells: list[list]) -> None:
        secsize = self._dr.sector_size
        idlen = self._dr.idlen
        alloc_start = self._zone_bit_span(zone)[0]
        end = self._zone_usable_end(zone)

        for byte in range(alloc_start // 8, (end + 7) // 8):
            self._map[byte] = 0

        b = alloc_start
        free_positions: list[int] = []
        for fid, length_bits in cells:
            if fid is not None:
                write_bits(self._map, b, idlen, fid)
            else:
                free_positions.append(b)
            write_bits(self._map, b + length_bits - 1, 1, 1)  # stop bit
            b += length_bits

        self._write_zone_free_chain(zone, free_positions)

        zone_bytes = bytearray(self._map[zone * secsize + i] for i in range(secsize))
        self._map[zone * secsize + _ZONE_CHECK_OFFSET] = calculate_zone_check(
            zone_bytes, 0, self._dr.log2_sector_size
        )
        for i in range(secsize):
            self._map[self._dr.nzones * secsize + zone * secsize + i] = self._map[
                zone * secsize + i
            ]

        self._build_index()

    def _id_per_zone(self) -> int:
        return (self._dr.sector_size * 8 - self._dr.zone_spare) // (self._dr.idlen + 1)

    def _allocate_multizone(self, length_bytes: int) -> int:
        need_bits = self._need_bits(length_bytes)
        id_per_zone = self._id_per_zone()
        nzones = self._dr.nzones
        used = set(self._fragments) | {0, 1, 2}

        for start_zone in range(nzones):
            low = max(start_zone * id_per_zone, 3)
            new_fid = next(
                (c for c in range(low, (start_zone + 1) * id_per_zone) if c not in used), None
            )
            if new_fid is None:
                continue

            # Gather free space across zones in the search order that begins at
            # the id's home zone and wraps — the order in which the fragments
            # will later be read back.
            zone_order = [(start_zone + k) % nzones for k in range(nzones)]
            planned: dict[int, list[list]] = {}
            remaining = need_bits
            for zone in zone_order:
                if remaining <= 0:
                    break
                cells = self._parse_zone_cells(zone)
                if not any(fid is None for fid, _ in cells):
                    continue
                new_cells = self._fill_free_cells(cells, new_fid, remaining)
                consumed = sum(ln for fid, ln in new_cells if fid == new_fid)
                if consumed:
                    planned[zone] = new_cells
                    remaining -= consumed
            if remaining > 0:
                continue  # not enough free space starting from this zone

            for zone, cells in planned.items():
                self._rewrite_zone(zone, cells)
            return new_fid << 8

        raise ADFSDiscFullError(f"not enough free space for {length_bytes} bytes")

    def _free_multizone(self, indirect: int) -> None:
        frag_id = indirect >> 8
        found = False
        # A multi-fragment object may span zones; free it in every zone.
        for zone in range(self._dr.nzones):
            cells = self._parse_zone_cells(zone)
            if not any(fid == frag_id for fid, _ in cells):
                continue
            found = True
            for cell in cells:
                if cell[0] == frag_id:
                    cell[0] = None
            merged: list[list] = []
            for fid, length_bits in cells:
                if fid is None and merged and merged[-1][0] is None:
                    merged[-1][1] += length_bits
                else:
                    merged.append([fid, length_bits])
            self._rewrite_zone(zone, merged)
        if not found:
            raise ADFSMapError(f"No allocated fragment for id 0x{frag_id:X}")

    def set_root_indirect(self, new_indirect: int) -> None:
        """Record a moved root's new indirect address in the disc record."""
        _write_le(self._map, _DISC_RECORD_OFFSET + 0x0C, new_indirect, 4)
        self._dr = replace(self._dr, root=new_indirect)
        self._refresh_zone(0)

    def _refresh_zone(self, zone: int) -> None:
        """Recompute a zone's check byte and re-duplicate it, without touching the bitmap."""
        secsize = self._dr.sector_size
        zone_bytes = bytearray(self._map[zone * secsize + i] for i in range(secsize))
        self._map[zone * secsize + _ZONE_CHECK_OFFSET] = calculate_zone_check(
            zone_bytes, 0, self._dr.log2_sector_size
        )
        for i in range(secsize):
            self._map[self._dr.nzones * secsize + zone * secsize + i] = self._map[
                zone * secsize + i
            ]

    def fragment_capacity(self, frag_id: int) -> int:
        """Total allocated bytes of a fragment id (0 if unallocated)."""
        fragments = self._fragments.get(frag_id)
        if not fragments:
            return 0
        return sum(capacity for _, capacity, _ in fragments)

    def fragment_count(self, frag_id: int) -> int:
        """Number of separate fragments an id occupies (sharing needs exactly one)."""
        return len(self._fragments.get(frag_id, ()))

    @property
    def min_fragment_bytes(self) -> int:
        """Smallest possible fragment: ``(idlen + 1)`` map bits."""
        return (self._dr.idlen + 1) * self._dr.bytes_per_map_bit

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
        """Validate every zone's check byte."""
        errors: list[ADFSValidationError] = []
        secsize = self._dr.sector_size
        for zone in range(self._dr.nzones):
            expected = self._map[zone * secsize + _ZONE_CHECK_OFFSET]
            calculated = calculate_zone_check(self._map, zone, self._dr.log2_sector_size)
            if expected != calculated:
                errors.append(
                    ADFSValidationError(
                        f"Zone {zone} check byte mismatch: stored 0x{expected:02X}, "
                        f"calculated 0x{calculated:02X}"
                    )
                )
        return errors


# --- Blank New Map creation ---

#: FileCore ``disctype`` word for the non-``+`` shapes (D/E/F).
_DISCTYPE_NON_PLUS = 0x20158C78
#: FileCore ``disctype`` word for the ``+`` shapes (E+/F+/G, Big directories).
_DISCTYPE_PLUS = 0x20158318
#: Default Big-directory root size, and E+'s root fragment id (first user id).
_BIG_DIR_ROOT_SIZE = 2048
_E_PLUS_ROOT_FRAGMENT = 3

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


def format_blank_single_zone(
    data: SectorsView,
    disc_record: DiscRecord,
    root_size: int,
    root_fragment_id: "int | None" = None,
) -> int:
    """Lay down a blank single-zone New Map; return the root's disc byte address.

    Writes, into *data* (the whole image), the zone header, disc record,
    allocation bitmap and its duplicate copy. By default the system fragment
    (id 2) covers the two map copies plus the root. When *root_fragment_id* is
    given (the E+ Big-directory case), the system fragment covers only the two
    map copies and the root is laid down as its own fragment right after — so
    it can later grow independently. The caller writes the empty root directory
    at the returned address.
    """
    if disc_record.nzones != 1:
        raise ADFSMapError("format_blank_single_zone only supports single-zone maps")
    secsize = disc_record.sector_size
    bpmb = disc_record.bytes_per_map_bit
    idlen = disc_record.idlen
    map_start_bit = _ZONE0_MAP_START * 8  # 512 — the disc address origin

    # System fragment (id 2): the two map copies, plus the root when it is not a
    # separate fragment.
    if root_fragment_id is None:
        system_bits = (secsize * 2 + root_size) // bpmb
    else:
        system_bits = (secsize * 2) // bpmb
    write_bits(data, map_start_bit, idlen, 2)
    write_bits(data, map_start_bit + system_bits - 1, 1, 1)  # fragment stop bit
    free_start_bit = map_start_bit + system_bits

    # Separate root fragment (Big directories) directly after the map copies.
    if root_fragment_id is not None:
        root_bits = root_size // bpmb
        write_bits(data, free_start_bit, idlen, root_fragment_id)
        write_bits(data, free_start_bit + root_bits - 1, 1, 1)
        free_start_bit += root_bits

    # Terminate the free region at the last usable map bit.
    eod_bit = disc_record.disc_size // bpmb
    write_bits(data, map_start_bit + eod_bit - 1, 1, 1)

    # FreeLink: 15-bit distance from the link (bit 8) to the sole free area,
    # with the terminator flag (0x8000) set.
    _write_le(data, _ZONE_FREELINK_OFFSET, 0x8000 | (free_start_bit - 8), 2)
    data[_ZONE_CROSSCHECK_OFFSET] = 0xFF

    disc_record.serialise(data)

    # Zone check over the finished zone, then duplicate the whole map.
    data[_ZONE_CHECK_OFFSET] = calculate_zone_check(data, 0, disc_record.log2_sector_size)
    for i in range(secsize):
        data[secsize + i] = data[i]

    return secsize * 2  # root disc byte address


# ADFS F: 1.6MB, four-zone New Map, boot block at 0xC00.
_F_ZONE_SPARE = 1600
_BOOT_BLOCK_OFFSET = 0xC00
_BOOT_BLOCK_SIZE = 0x200
_BOOT_CHECKSUM_OFFSET = 0xDFF
_PARTIAL_DISC_RECORD_OFFSET = 0xDC0


def f_disc_record(title: str, *, disc_id: int = 0, boot_option: int = 0) -> DiscRecord:
    """Build the disc record for a blank 1.6MB four-zone ADFS F disc."""
    return DiscRecord(
        log2_sector_size=10,
        sectors_per_track=10,
        heads=2,
        density=4,
        idlen=15,
        log2_bytes_per_map_bit=6,  # 64 bytes per map bit
        skew=1,
        boot_option=boot_option,
        low_sector=0,
        nzones=4,
        zone_spare=_F_ZONE_SPARE,
        root=0x209,
        disc_size=1638400,
        disc_id=disc_id,
        disc_name=title[:10],
        disc_type=_DISCTYPE_NON_PLUS,
    )


def e_plus_disc_record(title: str, *, disc_id: int = 0, boot_option: int = 0) -> DiscRecord:
    """Disc record for a blank 800K single-zone ADFS E+ disc (Big directories)."""
    dr = e_disc_record(title, disc_id=disc_id, boot_option=boot_option)
    return replace(
        dr,
        root=(_E_PLUS_ROOT_FRAGMENT << 8) | 1,
        disc_type=_DISCTYPE_PLUS,
        format_version=1,
        root_size=_BIG_DIR_ROOT_SIZE,
    )


def f_plus_disc_record(title: str, *, disc_id: int = 0, boot_option: int = 0) -> DiscRecord:
    """Disc record for a blank 1.6MB four-zone ADFS F+ disc (Big directories)."""
    dr = f_disc_record(title, disc_id=disc_id, boot_option=boot_option)
    root_fragment = (dr.nzones // 2) * (
        (dr.sector_size * 8 - dr.zone_spare) // (dr.idlen + 1)
    )
    return replace(
        dr,
        root=(root_fragment << 8) | 1,
        disc_type=_DISCTYPE_PLUS,
        format_version=1,
        root_size=_BIG_DIR_ROOT_SIZE,
    )


# ADFS G: 3.2MB, eight-zone New Map. The natural doubling of F — twice the
# sectors per track and twice the zones — keeping F's 1024-byte sectors,
# 64-byte map granularity and 15-bit ids. Octal density (8). No reference
# formatter writes G, so these values follow FileCore's map invariant
# (nzones*(8*secsize - zone_spare) - 480 >= disc_size/bpmb) and the New-dir
# root convention root = 0x200 | (nzones*2 + 1); verified by round-trip.
_G_ZONE_SPARE = _F_ZONE_SPARE  # 1600 bits, as F


def g_disc_record(title: str, *, disc_id: int = 0, boot_option: int = 0) -> DiscRecord:
    """Build the disc record for a blank 3.2MB eight-zone ADFS G disc."""
    return DiscRecord(
        log2_sector_size=10,
        sectors_per_track=20,
        heads=2,
        density=8,
        idlen=15,
        log2_bytes_per_map_bit=6,  # 64 bytes per map bit
        skew=1,
        boot_option=boot_option,
        low_sector=0,
        nzones=8,
        zone_spare=_G_ZONE_SPARE,
        root=0x211,  # 0x200 | (nzones*2 + 1)
        disc_size=3276800,
        disc_id=disc_id,
        disc_name=title[:10],
        disc_type=_DISCTYPE_NON_PLUS,
    )


def g_plus_disc_record(title: str, *, disc_id: int = 0, boot_option: int = 0) -> DiscRecord:
    """Disc record for a blank 3.2MB eight-zone ADFS G+ disc (Big directories)."""
    dr = g_disc_record(title, disc_id=disc_id, boot_option=boot_option)
    root_fragment = (dr.nzones // 2) * (
        (dr.sector_size * 8 - dr.zone_spare) // (dr.idlen + 1)
    )
    return replace(
        dr,
        root=(root_fragment << 8) | 1,
        disc_type=_DISCTYPE_PLUS,
        format_version=1,
        root_size=_BIG_DIR_ROOT_SIZE,
    )


def hard_drive_params(disc_size: int, *, big_map: bool = False, ide: bool = True) -> dict | None:
    """Compute New Map parameters for a hard disc of *disc_size* bytes.

    A faithful port of FileCore's ``InitDiscRec`` search (via DiscImageManager's
    ``ADFSGetHardDriveParams``): it walks ``log2bpmb``, ``zone_spare`` and
    ``idlen`` to find the smallest values that fit the disc, then derives the
    root address. Returns the parameter dict, or ``None`` if the size cannot be
    represented. The values are valid FileCore parameters; they need not match
    any particular formatter's choices (e.g. RISC OS HForm).
    """
    max_idlen = 21
    min_log2bpmb, max_log2bpmb = 8, 12
    min_zone_spare, max_zone_spare = 32, 128
    min_zones, max_zones = 1, 127
    zone0_bits = 8 * 60
    big_dir_min = 2048
    new_dir_size = 0x500
    log2secsize = 9 if ide else 8
    low_sector = 1 if ide else 0
    min_idlen = log2secsize + 3

    log2bpmb = min_log2bpmb
    while log2bpmb <= max_log2bpmb:
        disc_bits = disc_size >> log2bpmb
        zone_spare = min_zone_spare
        restart = False
        while zone_spare <= max_zone_spare:
            zone_bits = (8 << log2secsize) - zone_spare
            zones = min_zones
            cumulative = zone_bits - zone0_bits
            too_many = False
            while not cumulative > disc_bits:
                cumulative += zone_bits
                zones += 1
                if zones > max_zones:
                    too_many = True
                    break
            if too_many:
                restart = True
                break
            idlen = min_idlen
            while idlen <= max_idlen:
                ids_per_zone = zone_bits // (idlen + 1)
                if ids_per_zone * zones > (1 << idlen):
                    idlen += 1
                    continue
                spare_in_last = cumulative - disc_bits
                if spare_in_last == 0:
                    return _hd_result(idlen, zone_spare, zones, log2bpmb, log2secsize, low_sector)
                if spare_in_last < idlen:
                    idlen += 1
                    continue
                last_zone_bits = disc_bits - (cumulative - zone_bits)
                if last_zone_bits < idlen:
                    idlen += 1
                    continue
                if zones > 2:
                    return _hd_result(idlen, zone_spare, zones, log2bpmb, log2secsize, low_sector)
                # The last zone is the map zone: it must hold two map copies and
                # the root directory.
                map_bytes = zones * (2 << log2secsize)
                lfau_minus_1 = (1 << log2bpmb) - 1
                if not big_map:
                    map_bytes += new_dir_size
                else:
                    dir_bits = (lfau_minus_1 + big_dir_min) >> log2bpmb
                    if dir_bits <= idlen:
                        dir_bits = idlen + 1
                    last_zone_bits -= dir_bits
                    if last_zone_bits < 0:
                        idlen += 1
                        continue
                map_bits = (map_bytes + lfau_minus_1) >> log2bpmb
                if map_bits <= idlen:
                    map_bits = idlen + 1
                if last_zone_bits < map_bits:
                    idlen += 1
                    continue
                return _hd_result(idlen, zone_spare, zones, log2bpmb, log2secsize, low_sector)
            zone_spare += 1
        if restart:
            log2bpmb += 1
            continue
        log2bpmb += 1
    return None


def _hd_result(idlen, zone_spare, zones, log2bpmb, log2secsize, low_sector) -> dict:
    return {
        "idlen": idlen,
        "zone_spare": zone_spare,
        "nzones": zones,
        "log2_bytes_per_map_bit": log2bpmb,
        "log2_sector_size": log2secsize,
        "low_sector": low_sector,
        "root": (zones << 1) + 0x201,
    }


def hdd_disc_record(
    disc_size: int,
    title: str,
    *,
    big_directories: bool = False,
    disc_id: int = 0,
    boot_option: int = 0,
) -> DiscRecord:
    """Build a New Map hard disc's disc record for *disc_size* bytes.

    Raises ``ADFSMapError`` if the size cannot be represented as a New Map disc.
    """
    params = hard_drive_params(disc_size, big_map=big_directories)
    if params is None:
        raise ADFSMapError(f"cannot represent a {disc_size}-byte New Map hard disc")
    return DiscRecord(
        log2_sector_size=params["log2_sector_size"],
        sectors_per_track=63,  # IDE
        heads=16,  # IDE
        density=0,
        idlen=params["idlen"],
        log2_bytes_per_map_bit=params["log2_bytes_per_map_bit"],
        skew=0,
        boot_option=boot_option,
        low_sector=params["low_sector"],
        nzones=params["nzones"],
        zone_spare=params["zone_spare"],
        root=params["root"] if not big_directories else (params["root"] & ~0xFF) | 1,
        disc_size=disc_size,
        disc_id=disc_id,
        disc_name=title[:10],
        disc_type=_DISCTYPE_PLUS if big_directories else _DISCTYPE_NON_PLUS,
        format_version=1 if big_directories else 0,
        root_size=_BIG_DIR_ROOT_SIZE if big_directories else 0,
    )


def _boot_block_checksum(data: SectorsView, offset: int, size: int) -> int:
    """Additive-with-carry checksum (new-map accumulator 0), skipping the last byte."""
    acc = 0
    for p in range(size - 2, -1, -1):
        carry = acc >> 8
        acc &= 0xFF
        acc += data[offset + p] + carry
    return acc & 0xFF


def _write_hard_disc_hardware_info(data: SectorsView, dr: DiscRecord) -> None:
    """Write the boot block's hard-disc hardware fields (matching FileCore/HForm).

    Notably the *initialised* flag at 0xDBB, without which RISC OS treats the
    disc as unformatted, plus the parking cylinder and the 0xDAC marker.
    """
    _write_le(data, 0xDAC, 0xFFFFFFFF, 4)
    data[0xDBA] = 0x00  # LBA flag (IDE)
    data[0xDBB] = 0x01  # disc-initialised flag
    cylinder_bytes = dr.sectors_per_track * dr.heads * dr.sector_size
    cylinders = dr.disc_size // cylinder_bytes if cylinder_bytes else 0
    last = max(cylinders - 1, 0)
    if dr.uses_big_directories:
        parking = dr.sectors_per_track * dr.heads * last
    else:
        parking = dr.sector_size * dr.sectors_per_track * dr.heads * last
    _write_le(data, 0xDBC, parking & 0xFFFFFFFF, 4)


def _write_partial_disc_record(data: SectorsView, dr: DiscRecord) -> None:
    o = _PARTIAL_DISC_RECORD_OFFSET
    data[o + 0x00] = dr.log2_sector_size
    data[o + 0x01] = dr.sectors_per_track
    data[o + 0x02] = dr.heads
    data[o + 0x03] = dr.density
    data[o + 0x04] = dr.idlen
    data[o + 0x05] = dr.log2_bytes_per_map_bit
    data[o + 0x06] = dr.skew
    data[o + 0x08] = dr.low_sector
    data[o + 0x09] = dr.nzones
    _write_le(data, o + 0x0A, dr.zone_spare, 2)
    _write_le(data, o + 0x0C, dr.root, 4)
    _write_le(data, o + 0x10, dr.disc_size, 4)


def format_blank_f(
    data: SectorsView,
    disc_record: DiscRecord,
    root_size: int,
    root_fragment_id: "int | None" = None,
) -> int:
    """Lay down a blank four-zone ADFS F disc; return the root's disc byte address.

    *data* is the whole image. Writes the boot block (defect terminator, partial
    disc record, checksum), then the map at ``bootmap`` (mid-disc): a full disc
    record in zone 0, per-zone headers, the system fragment (id 2, split between
    zone 0 and the middle zone, covering the two map copies plus the root), the
    end-of-disc defect marker (id 1), per-zone free terminators and FreeLink
    chains, every zone's check byte, and the duplicate map copy.
    """
    dr = disc_record
    if dr.nzones <= 1:
        raise ADFSMapError("format_blank_f is for multi-zone discs")
    secsize = dr.sector_size
    bpmb = dr.bytes_per_map_bit
    idlen = dr.idlen
    nzones = dr.nzones
    zone_spare = dr.zone_spare
    bootmap = compute_bootmap(dr)

    # Boot block: defect-list terminator (0x20000000), hard-disc hardware info
    # (for hard discs), the partial disc record, and the checksum last.
    data[_BOOT_BLOCK_OFFSET + 3] = 0x20
    # Only actual hard discs (density 0) carry the hardware info; a G-format
    # floppy is larger than an F floppy but is still a floppy (octal density).
    if dr.density == 0:
        _write_hard_disc_hardware_info(data, dr)
    _write_partial_disc_record(data, dr)
    data[_BOOT_CHECKSUM_OFFSET] = _boot_block_checksum(
        data, _BOOT_BLOCK_OFFSET, _BOOT_BLOCK_SIZE
    )

    # Full disc record in zone 0, and per-zone cross-check bytes (0xFF marks the
    # last zone; the others are zero — their XOR is the single-zone 0xFF marker).
    dr.serialise(data, bootmap + 0x04)
    for zone in range(nzones):
        data[bootmap + zone * secsize + _ZONE_CROSSCHECK_OFFSET] = (
            0xFF if zone == nzones - 1 else 0x00
        )

    map_bit = bootmap * 8  # image-bit base of the map

    def alloc_start(zone: int) -> int:
        return zone * secsize * 8 + (_ZONE0_MAP_START * 8 if zone == 0 else _ZONE_HEADER_SIZE * 8)

    # System fragment (id 2): a part at the disc start (zone 0) and a part
    # covering the map area itself (the middle zone).
    middle = nzones // 2
    zone0_frag_bits = 0x1000 // bpmb
    # The map copies always sit in the middle zone; the root joins them unless
    # it is a separate fragment (Big directories).
    if root_fragment_id is None:
        middle_frag_bits = (secsize * nzones * 2 + root_size) // bpmb
    else:
        middle_frag_bits = (secsize * nzones * 2) // bpmb
    free_start = {zone: alloc_start(zone) for zone in range(nzones)}
    for zone, frag_bits in ((0, zone0_frag_bits), (middle, middle_frag_bits)):
        start = alloc_start(zone)
        write_bits(data, map_bit + start, idlen, 2)
        write_bits(data, map_bit + start + frag_bits - 1, 1, 1)  # stop bit
        free_start[zone] = start + frag_bits

    # Separate root fragment (Big directories) directly after the map copies.
    if root_fragment_id is not None:
        root_bits = root_size // bpmb
        start = free_start[middle]
        write_bits(data, map_bit + start, idlen, root_fragment_id)
        write_bits(data, map_bit + start + root_bits - 1, 1, 1)
        free_start[middle] = start + root_bits

    # Per-zone free terminators (end of each zone's usable region). The
    # position is measured from the end of the 4-byte zone header.
    terminator_rel = _ZONE_HEADER_SIZE * 8 + (secsize * 8 - zone_spare - 1)
    for zone in range(nzones):
        write_bits(data, map_bit + zone * secsize * 8 + terminator_rel, 1, 1)

    # End-of-disc marker: a terminator bit then a defect fragment (id 1).
    eod_bit = (dr.disc_size // bpmb) + zone_spare * (nzones - 1) + 480 + 32
    write_bits(data, map_bit + eod_bit - 1, 1, 1)
    write_bits(data, map_bit + eod_bit, idlen, 1)

    # FreeLink chains: each zone's header points to its single free area.
    for zone in range(nzones):
        header_bit = (zone * secsize + _ZONE_FREELINK_OFFSET) * 8
        distance = free_start[zone] - header_bit
        _write_le(data, bootmap + zone * secsize + _ZONE_FREELINK_OFFSET, 0x8000 | distance, 2)

    # Every zone's check byte (computed over a copy of that zone), then
    # duplicate the whole map into the second copy.
    for zone in range(nzones):
        zone_bytes = bytearray(
            data[bootmap + zone * secsize + i] for i in range(secsize)
        )
        data[bootmap + zone * secsize + _ZONE_CHECK_OFFSET] = calculate_zone_check(
            zone_bytes, 0, dr.log2_sector_size
        )
    for i in range(nzones * secsize):
        data[bootmap + nzones * secsize + i] = data[bootmap + i]

    return bootmap + nzones * secsize * 2  # root disc byte address

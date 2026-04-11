"""JesMap — per-object map sector listing its data extents.

Every file and directory in an AFS region has a **map sector**
(``JesMap``) identified by its SIN (system internal name). The map
sector lists the runs of data sectors (extents) that together make
up the object's contents. A file need not be contiguous on disc;
the map sector is how the file server stitches scattered extents
into a single sequential byte stream.

On-disc layout (256 bytes, little-endian throughout):

======  =========================================================
Offset  Meaning
======  =========================================================
  0-5   Magic ``'JesMap'``
    6   Map sequence number (leading copy)
    7   Unused
    8   Object size modulo 256 — bytes used in the last data
        sector. Zero means the object is an exact multiple of
        the sector size.
    9   Unused
   10   First extent: start sector (3 bytes, 24-bit LE)
   13   First extent: sector count (2 bytes LE)
   15   Second extent: start sector
   18   Second extent: sector count
   20   … (further extents, 5 bytes each)
  ...
  254   (end of final extent slot)
  255   Map sequence number (trailing copy — must match byte 6)
======  =========================================================

The extent list is terminated by a zero start sector, **not** by a
count — a file with fewer than the 49 available slots has zeros in
the unused tail. If byte 6 and byte 255 disagree, the file server
raises ``DRERRB`` ("broken directory"), which we surface as
:class:`AFSBrokenMapError`.

**Object size** is derived from the total extent length:

- If ``last_sector_bytes == 0``, the object is ``total_sectors * 256``
  bytes long — it fully uses its last sector.
- Otherwise it is ``(total_sectors - 1) * 256 + last_sector_bytes``
  — the last sector is partially used.

The empty-object case (zero extents) has size zero.

**Map chaining** for very large objects uses multiple map sectors
with incrementing sequence numbers. Phase 4 handles single-sector
maps only; phase 7 will extend this to the chained form after
MAPMAN (``Uade10``–``Uade13``) has been examined.

References:
    docs/afs-onwire.md §Map sector (JesMap).
    Beebmaster PDF pp.10-11 for the worked example.
    Uade02.asm:208-220 — MBENTS / ENSZ = 5 / MXENTS = 49.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from oaknut.afs.exceptions import AFSBrokenMapError
from oaknut.afs.types import Sector, SystemInternalName

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAGIC = b"JesMap"
MAP_SECTOR_SIZE = 256  # BLKSZE

_OFF_MAGIC = 0
_OFF_SEQ_LEADING = 6
_OFF_UNUSED_A = 7
_OFF_LAST_SECTOR_BYTES = 8
_OFF_UNUSED_B = 9
_OFF_EXTENTS = 10
_OFF_SEQ_TRAILING = 255

_EXTENT_SIZE = 5  # 3 bytes start sector + 2 bytes length
_MAX_EXTENTS = (_OFF_SEQ_TRAILING - _OFF_EXTENTS) // _EXTENT_SIZE  # 49


# ---------------------------------------------------------------------------
# Extent
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Extent:
    """A contiguous run of data sectors.

    ``start`` is a 24-bit sector address measured from the start of
    the physical disc (not the start of the AFS region — the map
    sector stores absolute sector numbers). ``length`` is in sectors.
    """

    start: Sector
    length: int

    def __post_init__(self) -> None:
        if not (0 < self.start <= 0xFFFFFF):
            # Start sector 0 is reserved as the end-of-list sentinel.
            raise ValueError(f"extent start {self.start} outside 1..0xFFFFFF")
        if not (0 < self.length <= 0xFFFF):
            raise ValueError(f"extent length {self.length} outside 1..0xFFFF")

    @property
    def end(self) -> Sector:
        """One past the last sector of the extent."""
        return Sector(self.start + self.length)

    def iter_sectors(self) -> Iterator[Sector]:
        for offset in range(self.length):
            yield Sector(self.start + offset)


# ---------------------------------------------------------------------------
# MapSector
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MapSector:
    """Parsed JesMap map sector.

    ``sin`` is the SIN that points at this map sector — the same
    value that appears in the directory entry and in the info sector
    for the root directory. The SIN is the sector *address*, so
    dereferencing it (reading that sector from disc) yields the map
    sector's 256 bytes.
    """

    sin: SystemInternalName
    extents: tuple[Extent, ...]
    last_sector_bytes: int = 0
    sequence_number: int = 0
    #: Whether this map sector is the last in a multi-map chain.
    #: Currently always True for phase 4 (single-chain only); the
    #: phase 7 chained-map work will set this per the ROM's rules.
    is_last: bool = field(default=True)

    def __post_init__(self) -> None:
        if not (0 <= self.sequence_number <= 0xFF):
            raise ValueError(f"sequence_number {self.sequence_number} outside 0..255")
        if not (0 <= self.last_sector_bytes <= 0xFF):
            raise ValueError(f"last_sector_bytes {self.last_sector_bytes} outside 0..255")
        if len(self.extents) > _MAX_EXTENTS:
            raise ValueError(
                f"too many extents: {len(self.extents)} (max {_MAX_EXTENTS} per map sector)"
            )
        # The empty-object case (zero extents) is allowed: an object
        # may legitimately be zero bytes long and still have a map
        # sector pointing at no data.

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------

    def total_sectors(self) -> int:
        """Sum of the lengths of every extent."""
        return sum(e.length for e in self.extents)

    def object_size_bytes(self) -> int:
        """Compute the object's byte length from its extent total."""
        total = self.total_sectors()
        if total == 0:
            return 0
        if self.last_sector_bytes == 0:
            return total * MAP_SECTOR_SIZE
        return (total - 1) * MAP_SECTOR_SIZE + self.last_sector_bytes

    def iter_sectors(self) -> Iterator[Sector]:
        """Yield every data sector address in order."""
        for extent in self.extents:
            yield from extent.iter_sectors()

    def sector_at_offset(self, byte_offset: int) -> tuple[Sector, int]:
        """Translate a byte offset in the logical stream to (sector, offset_in_sector).

        Raises :class:`IndexError` if the byte offset is outside the
        object. This is the primitive the higher layers will use to
        implement ``read_bytes`` against a non-contiguous file.
        """
        if byte_offset < 0:
            raise IndexError(f"byte offset {byte_offset} is negative")
        if byte_offset >= self.object_size_bytes():
            raise IndexError(
                f"byte offset {byte_offset} is past end of object "
                f"({self.object_size_bytes()} bytes)"
            )
        target_sector_index = byte_offset // MAP_SECTOR_SIZE
        offset_in_sector = byte_offset % MAP_SECTOR_SIZE
        # Walk the extents to find the right sector.
        sector_cursor = 0
        for extent in self.extents:
            if sector_cursor + extent.length > target_sector_index:
                local = target_sector_index - sector_cursor
                return Sector(extent.start + local), offset_in_sector
            sector_cursor += extent.length
        # The bounds check above should have prevented this.
        raise AssertionError(
            f"sector_at_offset: failed to locate byte {byte_offset} in "
            f"{self.total_sectors()}-sector object"
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialise to the 256-byte on-disc form."""
        buf = bytearray(MAP_SECTOR_SIZE)
        buf[_OFF_MAGIC : _OFF_MAGIC + len(MAGIC)] = MAGIC
        buf[_OFF_SEQ_LEADING] = self.sequence_number
        buf[_OFF_LAST_SECTOR_BYTES] = self.last_sector_bytes

        cursor = _OFF_EXTENTS
        for extent in self.extents:
            buf[cursor : cursor + 3] = int(extent.start).to_bytes(3, "little")
            buf[cursor + 3 : cursor + 5] = extent.length.to_bytes(2, "little")
            cursor += _EXTENT_SIZE

        buf[_OFF_SEQ_TRAILING] = self.sequence_number
        return bytes(buf)

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        sin: SystemInternalName,
    ) -> MapSector:
        """Parse a map sector's 256 bytes.

        The caller must supply the SIN that was used to locate this
        sector — we cannot recover it from the bytes alone and it's
        needed on the returned object so upper layers can re-read it.
        """
        if len(data) != MAP_SECTOR_SIZE:
            raise AFSBrokenMapError(f"map sector must be {MAP_SECTOR_SIZE} bytes, got {len(data)}")
        if data[_OFF_MAGIC : _OFF_MAGIC + len(MAGIC)] != MAGIC:
            raise AFSBrokenMapError(
                f"bad map magic: {bytes(data[_OFF_MAGIC : _OFF_MAGIC + len(MAGIC)])!r} != {MAGIC!r}"
            )
        leading_seq = data[_OFF_SEQ_LEADING]
        trailing_seq = data[_OFF_SEQ_TRAILING]
        if leading_seq != trailing_seq:
            raise AFSBrokenMapError(
                f"map sector sequence-number mismatch: "
                f"leading={leading_seq:#x} trailing={trailing_seq:#x}"
            )

        last_sector_bytes = data[_OFF_LAST_SECTOR_BYTES]

        # Walk extents until we hit a zero start sector.
        extents: list[Extent] = []
        cursor = _OFF_EXTENTS
        for _ in range(_MAX_EXTENTS):
            start = int.from_bytes(data[cursor : cursor + 3], "little")
            if start == 0:
                break
            length = int.from_bytes(data[cursor + 3 : cursor + 5], "little")
            if length == 0:
                raise AFSBrokenMapError(
                    f"map sector has extent with nonzero start {start:#x} "
                    f"but zero length at offset {cursor:#x}"
                )
            extents.append(Extent(Sector(start), length))
            cursor += _EXTENT_SIZE

        try:
            return cls(
                sin=sin,
                extents=tuple(extents),
                last_sector_bytes=last_sector_bytes,
                sequence_number=leading_seq,
            )
        except ValueError as exc:
            raise AFSBrokenMapError(f"invalid map sector: {exc}") from exc


# ---------------------------------------------------------------------------
# ExtentStream — a byte-addressable view over a MapSector
# ---------------------------------------------------------------------------


#: Callback signature for reading a data sector by absolute sector
#: address. The allocator/upper layers wire this to a
#: :class:`oaknut.discimage.SectorsView` slice.
DataSectorReader = type(lambda s: b"")  # placeholder for docs; see below


class ExtentStream:
    """Byte-addressable view over a :class:`MapSector`'s data.

    The stream reads data on demand through a supplied callback,
    which is given an absolute sector address and must return the
    256-byte sector contents. This makes the stream testable without
    a real :class:`SectorsView`: a dict-backed mock reader is all
    that's needed.

    The callback is called lazily — no read happens until bytes are
    actually requested — and the stream does not cache, so callers
    that want caching should wrap the callback.
    """

    def __init__(
        self,
        map_sector: MapSector,
        reader,  # Callable[[Sector], bytes]
    ) -> None:
        self._map = map_sector
        self._reader = reader

    @property
    def size(self) -> int:
        return self._map.object_size_bytes()

    def read_all(self) -> bytes:
        """Return the full object contents as a single bytes object."""
        return self.read(0, self.size)

    def read(self, offset: int, length: int) -> bytes:
        """Return ``length`` bytes starting at ``offset``."""
        if length < 0:
            raise ValueError(f"length must be non-negative, got {length}")
        if length == 0:
            return b""
        if offset < 0 or offset + length > self.size:
            raise IndexError(
                f"read of [{offset}, {offset + length}) outside object [0, {self.size})"
            )

        result = bytearray()
        remaining = length
        cur_offset = offset

        while remaining > 0:
            sector, sector_off = self._map.sector_at_offset(cur_offset)
            chunk = self._reader(sector)
            if len(chunk) != MAP_SECTOR_SIZE:
                raise ValueError(
                    f"reader returned {len(chunk)} bytes for sector "
                    f"{sector:#x} (expected {MAP_SECTOR_SIZE})"
                )
            take = min(MAP_SECTOR_SIZE - sector_off, remaining)
            result += chunk[sector_off : sector_off + take]
            remaining -= take
            cur_offset += take

        return bytes(result)

"""JesMap — per-object map sector listing its data extents.

Every file and directory in an AFS region has a **map sector**
(``JesMap``) identified by its SIN (system internal name). The map
sector lists the runs of data sectors (extents) that together make
up the object's contents. A file need not be contiguous on disc;
the map sector is how the file server stitches scattered extents
into a single sequential byte stream.

On-disc layout (256 bytes, little-endian throughout, per
``Uade02:313-334``):

======  =========================================================
Offset  Meaning
======  =========================================================
  0-5   Magic ``'JesMap'`` (on disc). In memory the server
        replaces these bytes with ``BLKSN`` / ``BLKNO``.
    6   Map sequence number (leading copy, ``MBSQNO``)
    7   Reserved flags byte (``MGFLG``, always zero)
  8-9   Bytes-in-last-block, 16-bit LE (``BILB``). Only the
        final block in a chain carries a meaningful value; the
        value in intermediate blocks is stale. Zero means "last
        data sector is fully used".
 10-14  Slot 0: first data extent (3-byte start sector + 2-byte
        length, LE)
 15-19  Slot 1: second data extent
  ...   Slots 2..47 hold further data extents, 48 in total
 250-254 Slot 48 (``LSTENT``): **reserved for the chain pointer**.
        Holds either zero (end-of-chain) or ``(next_map_SIN, 1)``
        pointing at the next map block. Never a data extent.
   255  Trailing sequence number copy (``LSTSQ``) — must match
        the leading copy at offset 6.
======  =========================================================

**The 49th slot is always the chain pointer, never data**. The
server's write path at ``Uade12.asm:187-227`` (``MKRLN`` /
``ALBLK``) stores ``(newblock_SIN, 1)`` there when a file grows
past 48 extents. The read path at ``Uade13.asm:462-533``
(``MPGTSZ``) treats any non-zero entry at or beyond ``LSTENT``
as a chain pointer, loads the successor block via ``RDMPBK``,
and restarts the extent walk. So the maximum data extents per
map block is **48**, not 49.

Terminating a chain uses a zero start-sector, either in a slot
0..47 (file ended mid-block) or at slot 48 (file exactly fills
slots 0..47 and needs no successor).

**Object size** is derived from the total extent length plus the
final block's ``BILB``:

- If ``last_sector_bytes == 0``, the object's last sector is
  fully used → size is ``total_sectors * 256``.
- Otherwise it is ``(total_sectors - 1) * 256 + last_sector_bytes``.

The empty-object case (zero extents in the head block) has size
zero.

References:
    docs/afs-onwire.md §Map sector (JesMap).
    Beebmaster PDF pp.10-11 for the worked example.
    Uade02.asm:313-334 — MBENTS / ENSZ = 5 / MXENTS = 49 / LSTENT.
    Uade10.asm:58-236 — MPCRSP (magic write).
    Uade12.asm:187-227 — MKRLN / ALBLK (chain link construction).
    Uade13.asm:462-595 — MPGTSZ / MPGSNX / MPGSFN (chain traversal).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Optional

from oaknut.afs.exceptions import AFSBrokenMapError
from oaknut.afs.types import Sector, SystemInternalName

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAGIC = b"JesMap"
MAP_SECTOR_SIZE = 256  # BLKSZE (Uade01:254)

# Field offsets (Uade02:313-334).
_OFF_MAGIC = 0
_OFF_SEQ_LEADING = 6  # MBSQNO
_OFF_FLAGS = 7  # MGFLG — reserved
_OFF_LAST_SECTOR_BYTES = 8  # BILB — 16-bit LE, meaningful only in final block
_OFF_EXTENTS = 10  # MBENTS
_OFF_SEQ_TRAILING = 255  # LSTSQ

_EXTENT_SIZE = 5  # ENSZ — 3-byte start sector + 2-byte length
_TOTAL_SLOTS = 49  # MXENTS — total extent slots per map block
_MAX_DATA_EXTENTS = 48  # slots 0..47 hold data; slot 48 is the chain pointer
_CHAIN_SLOT_OFFSET = _OFF_EXTENTS + _MAX_DATA_EXTENTS * _EXTENT_SIZE  # 250 (LSTENT)
assert _CHAIN_SLOT_OFFSET == 250


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

    ``extents`` holds this block's **data** extents (at most 48 —
    slot 48 is reserved for the chain pointer). ``next_sin`` is
    ``None`` when this block is the last in its chain, or the SIN
    of the successor block otherwise.

    ``last_sector_bytes`` is the 16-bit ``BILB`` field. For a
    chained object it is only meaningful on the final block; the
    :class:`MapChain` wrapper uses the final block's value when
    computing the object's byte length.
    """

    sin: SystemInternalName
    extents: tuple[Extent, ...]
    last_sector_bytes: int = 0
    sequence_number: int = 0
    next_sin: Optional[SystemInternalName] = None

    def __post_init__(self) -> None:
        if not (0 <= self.sequence_number <= 0xFF):
            raise ValueError(f"sequence_number {self.sequence_number} outside 0..255")
        if not (0 <= self.last_sector_bytes <= 0xFFFF):
            raise ValueError(f"last_sector_bytes {self.last_sector_bytes} outside 0..0xFFFF")
        if len(self.extents) > _MAX_DATA_EXTENTS:
            raise ValueError(
                f"too many data extents: {len(self.extents)} "
                f"(max {_MAX_DATA_EXTENTS} per map block — slot 48 is the chain pointer)"
            )
        if self.next_sin is not None:
            if not (0 < int(self.next_sin) <= 0xFFFFFF):
                raise ValueError(f"next_sin {self.next_sin} outside 1..0xFFFFFF")
            # A chain pointer in slot 48 is only reachable when all 48
            # data slots are used — otherwise MPGSGB at Uade13:534
            # terminates the walk on the first zero-start entry and
            # the chain pointer is never consulted. Reject the
            # inconsistent combination at construction time so tests
            # and synthesised fixtures cannot drift from the ROM.
            if len(self.extents) != _MAX_DATA_EXTENTS:
                raise ValueError(
                    f"next_sin set but only {len(self.extents)} data extents present; "
                    f"the chain pointer at slot {_MAX_DATA_EXTENTS} is only reachable "
                    f"when all {_MAX_DATA_EXTENTS} data slots are full"
                )

    @property
    def is_last(self) -> bool:
        """True when no successor map block is chained after this one."""
        return self.next_sin is None
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
        buf[_OFF_LAST_SECTOR_BYTES : _OFF_LAST_SECTOR_BYTES + 2] = (
            self.last_sector_bytes.to_bytes(2, "little")
        )

        cursor = _OFF_EXTENTS
        for extent in self.extents:
            buf[cursor : cursor + 3] = int(extent.start).to_bytes(3, "little")
            buf[cursor + 3 : cursor + 5] = extent.length.to_bytes(2, "little")
            cursor += _EXTENT_SIZE

        # Slot 48 (LSTENT) — chain pointer if this block has a successor.
        if self.next_sin is not None:
            buf[_CHAIN_SLOT_OFFSET : _CHAIN_SLOT_OFFSET + 3] = int(self.next_sin).to_bytes(
                3, "little"
            )
            buf[_CHAIN_SLOT_OFFSET + 3 : _CHAIN_SLOT_OFFSET + 5] = (1).to_bytes(2, "little")

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

        last_sector_bytes = int.from_bytes(
            bytes(data[_OFF_LAST_SECTOR_BYTES : _OFF_LAST_SECTOR_BYTES + 2]), "little"
        )

        # Walk slots 0..47 as data extents, stopping at the first zero
        # start sector. See Uade13:462-533 (MPGTSZ / MPGSGB).
        extents: list[Extent] = []
        ended_early = False
        for slot in range(_MAX_DATA_EXTENTS):
            cursor = _OFF_EXTENTS + slot * _EXTENT_SIZE
            start = int.from_bytes(bytes(data[cursor : cursor + 3]), "little")
            if start == 0:
                ended_early = True
                break
            length = int.from_bytes(bytes(data[cursor + 3 : cursor + 5]), "little")
            if length == 0:
                raise AFSBrokenMapError(
                    f"map sector has extent with nonzero start {start:#x} "
                    f"but zero length at offset {cursor:#x}"
                )
            extents.append(Extent(Sector(start), length))

        # Slot 48 (LSTENT) — chain pointer or end-of-chain sentinel.
        # Uade13:488-492 (MPGSNX) treats a non-zero entry at or beyond
        # LSTENT as a chain pointer unconditionally; slot 48 is never
        # a data extent.
        next_sin: Optional[SystemInternalName] = None
        if not ended_early:
            chain_start = int.from_bytes(
                bytes(data[_CHAIN_SLOT_OFFSET : _CHAIN_SLOT_OFFSET + 3]), "little"
            )
            if chain_start != 0:
                next_sin = SystemInternalName(chain_start)

        try:
            return cls(
                sin=sin,
                extents=tuple(extents),
                last_sector_bytes=last_sector_bytes,
                sequence_number=leading_seq,
                next_sin=next_sin,
            )
        except ValueError as exc:
            raise AFSBrokenMapError(f"invalid map sector: {exc}") from exc


# ---------------------------------------------------------------------------
# MapChain — one or more linked MapSectors forming a single object's map
# ---------------------------------------------------------------------------


#: Signature of a "read a sector" callback supplied by the upper layers.
#: Given an absolute sector address, return its 256 bytes.
SectorReader = Callable[[Sector], bytes]

#: Signature of a "read a map block" callback: given a SIN, return the
#: parsed :class:`MapSector` at that address. Usually implemented by
#: :meth:`oaknut.afs.afs.AFS._read_map_sector`.
MapBlockReader = Callable[[SystemInternalName], "MapSector"]


@dataclass(frozen=True, slots=True)
class MapChain:
    """One or more :class:`MapSector` instances that together describe
    a single object.

    For the common case — an object whose extents fit inside a single
    map block — the chain has length 1 and behaves exactly like the
    pre-phase-7 single-block read path did. Larger objects chain
    multiple map blocks via the 49th extent slot; the chain is walked
    from the head SIN forward and flattened into one extent list.

    Chain construction reads every block in the chain eagerly. That
    keeps ``object_size_bytes`` and ``sector_at_offset`` O(1) against
    the flat extent list rather than needing to re-read blocks from
    disc on each access. For typical objects chains are short (one or
    two blocks), so the eager read is cheap.
    """

    blocks: tuple[MapSector, ...]

    def __post_init__(self) -> None:
        if not self.blocks:
            raise ValueError("MapChain must contain at least one map block")

    # ------------------------------------------------------------------
    # Construction from disc
    # ------------------------------------------------------------------

    @classmethod
    def walk(cls, head_sin: SystemInternalName, read_map: MapBlockReader) -> MapChain:
        """Walk the chain starting at ``head_sin``, reading each block.

        ``read_map`` is the SIN→MapSector dereferencer — the AFS
        handle supplies it. Raises :class:`AFSBrokenMapError` if a
        cycle is detected.
        """
        blocks: list[MapSector] = []
        seen: set[int] = set()
        current_sin: Optional[SystemInternalName] = head_sin
        while current_sin is not None:
            sin_int = int(current_sin)
            if sin_int in seen:
                raise AFSBrokenMapError(
                    f"cycle in map chain at sin {sin_int:#x}"
                )
            seen.add(sin_int)
            block = read_map(current_sin)
            blocks.append(block)
            current_sin = block.next_sin
        return cls(tuple(blocks))

    # ------------------------------------------------------------------
    # Derived values (flattened across all blocks)
    # ------------------------------------------------------------------

    @property
    def head(self) -> MapSector:
        return self.blocks[0]

    @property
    def last(self) -> MapSector:
        return self.blocks[-1]

    def flat_extents(self) -> tuple[Extent, ...]:
        """Concatenation of every block's data extents, in chain order."""
        result: list[Extent] = []
        for block in self.blocks:
            result.extend(block.extents)
        return tuple(result)

    def total_sectors(self) -> int:
        return sum(e.length for b in self.blocks for e in b.extents)

    def object_size_bytes(self) -> int:
        """Total byte length of the object.

        Uses the **final** block's ``last_sector_bytes`` — per
        ``Uade13:573-595`` (``MPGSFN``), only the final block's BILB
        value is consulted. Zero means "last data sector fully used",
        otherwise it is the number of bytes occupied in that sector.
        """
        total = self.total_sectors()
        if total == 0:
            return 0
        last_bytes = self.last.last_sector_bytes
        if last_bytes == 0:
            return total * MAP_SECTOR_SIZE
        return (total - 1) * MAP_SECTOR_SIZE + last_bytes

    def iter_sectors(self) -> Iterator[Sector]:
        for extent in self.flat_extents():
            yield from extent.iter_sectors()

    def sector_at_offset(self, byte_offset: int) -> tuple[Sector, int]:
        """Translate a byte offset to (absolute sector, offset_in_sector)."""
        if byte_offset < 0:
            raise IndexError(f"byte offset {byte_offset} is negative")
        size = self.object_size_bytes()
        if byte_offset >= size:
            raise IndexError(f"byte offset {byte_offset} is past end of object ({size} bytes)")
        target_sector_index = byte_offset // MAP_SECTOR_SIZE
        offset_in_sector = byte_offset % MAP_SECTOR_SIZE
        cursor = 0
        for extent in self.flat_extents():
            if cursor + extent.length > target_sector_index:
                local = target_sector_index - cursor
                return Sector(extent.start + local), offset_in_sector
            cursor += extent.length
        raise AssertionError(  # pragma: no cover
            f"sector_at_offset: failed to locate byte {byte_offset}"
        )


# ---------------------------------------------------------------------------
# ExtentStream — a byte-addressable view over a MapSector or MapChain
# ---------------------------------------------------------------------------


class ExtentStream:
    """Byte-addressable view over a :class:`MapSector` or :class:`MapChain`.

    The stream reads data on demand through a supplied callback,
    which is given an absolute sector address and must return the
    256-byte sector contents. This makes the stream testable without
    a real :class:`SectorsView`: a dict-backed mock reader is all
    that's needed.

    For single-block objects you can still pass a :class:`MapSector`
    directly; the stream wraps it in a one-block :class:`MapChain`
    internally. Multi-block reads require a pre-built chain (obtain
    one via :meth:`MapChain.walk` at the AFS layer).

    The callback is called lazily — no read happens until bytes are
    actually requested — and the stream does not cache, so callers
    that want caching should wrap the callback.
    """

    def __init__(
        self,
        map_obj: "MapSector | MapChain",
        reader: SectorReader,
    ) -> None:
        if isinstance(map_obj, MapSector):
            self._chain = MapChain(blocks=(map_obj,))
        else:
            self._chain = map_obj
        self._reader = reader

    @property
    def size(self) -> int:
        return self._chain.object_size_bytes()

    @property
    def chain(self) -> MapChain:
        return self._chain

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
            sector, sector_off = self._chain.sector_at_offset(cur_offset)
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

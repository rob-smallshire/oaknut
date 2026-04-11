"""AFS directory objects — parse and serialise.

An AFS directory is a variable-length object (a whole number of
sectors, typically 2) with a 17-byte header, a series of 26-byte
entry slots, and a 1-byte trailing master-sequence-number copy at
the final byte. Two linked lists thread through the slots: one for
in-use entries (kept in alphabetical order by the link chain) and
one for free slots.

On-disc layout (see ``docs/afs-onwire.md`` §Directory header and
§Directory entry, and ``Uade02.asm:77-95``):

Header (17 bytes at offset 0):

======  =========================================================
Offset  Meaning
======  =========================================================
 0-1    ``DRFRST`` — byte offset of the first in-use entry
                    (0 = empty list)
   2    ``DRSQNO`` — leading master sequence number
 3-12   ``DRNAME`` — directory name (10 bytes, space-padded)
13-14   ``DRFREE`` — byte offset of the first free slot
15-16   ``DRENTS`` — count of in-use entries
======  =========================================================

Each entry (26 bytes, slots start at offset 17):

======  =========================================================
Offset  Meaning
======  =========================================================
 0-1    ``DRLINK`` — pointer to next entry (0 = end of list)
 2-11   ``DRTITL`` — text name, space-padded
12-15   ``DRLOAD`` — load address (LE)
16-19   ``DREXEC`` — execute address (LE)
  20    ``DRACCS`` — access byte (see :class:`AFSAccess`)
21-22   ``DRDATE`` — packed creation date
23-25   ``DRSIN`` — SIN of object (24-bit LE)
======  =========================================================

The final byte of the directory object is the trailing copy of the
master sequence number — if it disagrees with byte 2, the file
server raises ``DRERRB`` ("broken directory") and we surface this
as :class:`AFSBrokenDirectoryError`.

**Capacity vs entry count.** ``DRENTS`` is the number of *in-use*
entries, not the slot capacity. The capacity is derived from the
directory's allocated size: ``(size_in_bytes - 18) // 26``, capped
at 255. A default 2-sector (512-byte) directory thus holds up to 19
slots, and a maximum 26-sector directory holds 255.

**Insertion order.** The file server fills the slot array from the
end — new entries get the highest-numbered free slot, which the
free-list pointer chain makes natural. The in-use list is walked
in alphabetical order (via the ``DRLINK`` chain) regardless of
physical slot layout.

Phase 5 covers read only. Insert/delete/grow come in phases 9-10.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from oaknut.afs.access import AFSAccess
from oaknut.afs.exceptions import AFSBrokenDirectoryError
from oaknut.afs.types import AfsDate, SystemInternalName

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADER_SIZE = 17  # DRSTAR offset (Uade02:83)
ENTRY_SIZE = 26  # DRENSZ (Uade02:95)
TRAILING_SEQ_SIZE = 1
MIN_DIRECTORY_SIZE = HEADER_SIZE + TRAILING_SEQ_SIZE  # 18 bytes, zero entries

#: Maximum entries per directory — ``Uade02:69-70`` states that
#: ``DRENTS`` is a 16-bit field but only the low byte is used
#: because the server does not support more than 255 entries.
MAX_ENTRIES = 255

#: Maximum directory name length — ``NAMLNT`` in ``Uade02:120``.
MAX_NAME_LENGTH = 10

# Header field offsets
_OFF_FIRST_POINTER = 0
_OFF_MASTER_SEQ = 2
_OFF_NAME = 3
_OFF_FREE_POINTER = 13
_OFF_NUM_ENTRIES = 15

# Entry field offsets
_ENT_OFF_LINK = 0
_ENT_OFF_NAME = 2
_ENT_OFF_LOAD = 12
_ENT_OFF_EXEC = 16
_ENT_OFF_ACCESS = 20
_ENT_OFF_DATE = 21
_ENT_OFF_SIN = 23


# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------


def _encode_name(name: str) -> bytes:
    """Encode a 10-byte space-padded object name."""
    if not name:
        raise ValueError("object name must not be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"object name {name!r} exceeds {MAX_NAME_LENGTH} characters")
    # The on-disc name may contain any printable ASCII except the
    # separator character and the space (used as pad). We only
    # enforce length and non-emptiness here; callers may validate
    # character sets at a higher layer.
    return name.encode("ascii").ljust(MAX_NAME_LENGTH, b" ")


def _decode_name(raw: bytes) -> str:
    if len(raw) != MAX_NAME_LENGTH:
        raise ValueError(f"object name field must be {MAX_NAME_LENGTH} bytes, got {len(raw)}")
    return raw.rstrip(b" \x00").decode("ascii")


# ---------------------------------------------------------------------------
# Directory entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DirectoryEntry:
    """A single parsed directory entry.

    This represents the data we actually care about for a slot;
    internal fields like the link pointer are hidden from callers
    and handled by the directory parser.
    """

    name: str
    load_address: int
    exec_address: int
    access: AFSAccess
    date: AfsDate
    sin: SystemInternalName

    def __post_init__(self) -> None:
        _encode_name(self.name)  # validates length and charset
        if not (0 <= self.load_address <= 0xFFFFFFFF):
            raise ValueError(f"load_address {self.load_address} outside 0..0xFFFFFFFF")
        if not (0 <= self.exec_address <= 0xFFFFFFFF):
            raise ValueError(f"exec_address {self.exec_address} outside 0..0xFFFFFFFF")
        if not (0 <= self.sin <= 0xFFFFFF):
            raise ValueError(f"sin {self.sin} outside 0..0xFFFFFF")

    @property
    def is_directory(self) -> bool:
        return self.access.is_directory

    @property
    def is_locked(self) -> bool:
        return self.access.is_locked


# ---------------------------------------------------------------------------
# AfsDirectory — the whole parsed directory object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AfsDirectory:
    """A parsed AFS directory.

    This phase (5) exposes a read-only view over a directory's
    contents: the name, master sequence number, the list of entries
    in alphabetical order (as threaded by the in-use link chain),
    and the slot capacity derived from the directory's byte size.
    Write operations come in phase 9.
    """

    name: str
    master_sequence_number: int
    entries: tuple[DirectoryEntry, ...]
    capacity: int
    #: The raw bytes this directory was parsed from, preserved so
    #: that a future mutation can edit in place without rebuilding
    #: from scratch. Phase 5 doesn't mutate, so this is informational.
    size_in_bytes: int

    def __post_init__(self) -> None:
        if not (0 <= self.master_sequence_number <= 0xFF):
            raise ValueError(f"master_sequence_number {self.master_sequence_number} outside 0..255")
        if not (0 <= self.capacity <= MAX_ENTRIES):
            raise ValueError(f"capacity {self.capacity} outside 0..{MAX_ENTRIES}")
        if len(self.entries) > self.capacity:
            raise ValueError(f"entries ({len(self.entries)}) exceeds capacity ({self.capacity})")
        # Entries should be in alphabetical order per the in-use list
        # invariant. This is a cross-check on our parser, not a
        # contract with callers — at higher layers a client who
        # constructs an AfsDirectory by hand might supply entries in
        # any order, so we allow it here and let :meth:`to_bytes`
        # (phase 9) sort them before writing.

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[DirectoryEntry]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, key: str | int) -> DirectoryEntry:
        if isinstance(key, int):
            return self.entries[key]
        return self.find(key)

    def find(self, name: str) -> DirectoryEntry:
        """Case-insensitive lookup by name.

        Raises :class:`KeyError` if not found.
        """
        name_upper = name.upper()
        for entry in self.entries:
            if entry.name.upper() == name_upper:
                return entry
        raise KeyError(f"no entry named {name!r} in directory {self.name!r}")

    def contains(self, name: str) -> bool:
        try:
            self.find(name)
        except KeyError:
            return False
        return True

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> AfsDirectory:
        """Parse a directory object from its full byte image.

        ``data`` must be the full object bytes (typically 512 bytes
        for a default 2-sector directory; up to 6656 for a maximum
        26-sector one). The parser derives the slot capacity from
        the length.
        """
        if len(data) < MIN_DIRECTORY_SIZE:
            raise AFSBrokenDirectoryError(
                f"directory too small: {len(data)} bytes (need at least {MIN_DIRECTORY_SIZE})"
            )

        leading_seq = data[_OFF_MASTER_SEQ]
        trailing_seq = data[len(data) - 1]
        if leading_seq != trailing_seq:
            raise AFSBrokenDirectoryError(
                f"directory master-sequence-number mismatch: "
                f"leading={leading_seq:#x} trailing={trailing_seq:#x}"
            )

        try:
            name = _decode_name(bytes(data[_OFF_NAME : _OFF_NAME + MAX_NAME_LENGTH]))
        except (UnicodeDecodeError, ValueError) as exc:
            raise AFSBrokenDirectoryError(f"bad directory name: {exc}") from exc

        first_pointer = int.from_bytes(data[_OFF_FIRST_POINTER : _OFF_FIRST_POINTER + 2], "little")
        num_entries = int.from_bytes(data[_OFF_NUM_ENTRIES : _OFF_NUM_ENTRIES + 2], "little")
        if num_entries > MAX_ENTRIES:
            raise AFSBrokenDirectoryError(f"num_entries {num_entries} exceeds {MAX_ENTRIES}")

        capacity = (len(data) - HEADER_SIZE - TRAILING_SEQ_SIZE) // ENTRY_SIZE
        if capacity > MAX_ENTRIES:
            capacity = MAX_ENTRIES

        # Walk the in-use linked list.
        entries = _walk_in_use_list(data, first_pointer, num_entries, capacity)

        return cls(
            name=name,
            master_sequence_number=leading_seq,
            entries=tuple(entries),
            capacity=capacity,
            size_in_bytes=len(data),
        )


# ---------------------------------------------------------------------------
# Linked-list walker
# ---------------------------------------------------------------------------


def _walk_in_use_list(
    data: bytes,
    first_pointer: int,
    expected_count: int,
    capacity: int,
) -> list[DirectoryEntry]:
    """Follow the in-use link chain starting at ``first_pointer``.

    Validates that pointers land on valid slot boundaries, detects
    cycles, and verifies the final count matches the header's
    ``DRENTS``. A length or bounds error raises
    :class:`AFSBrokenDirectoryError`.
    """
    results: list[DirectoryEntry] = []
    seen: set[int] = set()
    pointer = first_pointer

    while pointer != 0:
        if pointer < HEADER_SIZE:
            raise AFSBrokenDirectoryError(f"in-use list pointer {pointer:#x} below header")
        slot_offset = pointer - HEADER_SIZE
        if slot_offset % ENTRY_SIZE != 0:
            raise AFSBrokenDirectoryError(
                f"in-use list pointer {pointer:#x} not on a slot boundary"
            )
        slot_index = slot_offset // ENTRY_SIZE
        if slot_index >= capacity:
            raise AFSBrokenDirectoryError(
                f"in-use list pointer {pointer:#x} (slot {slot_index}) outside capacity {capacity}"
            )
        if pointer in seen:
            raise AFSBrokenDirectoryError(f"cycle in in-use list at pointer {pointer:#x}")
        seen.add(pointer)

        entry, next_pointer = _parse_slot(data, pointer)
        results.append(entry)
        pointer = next_pointer

        if len(results) > expected_count + 1:
            # Guard against runaway chains even though the seen-set
            # already catches cycles. If we've walked more entries
            # than the header claims, something is broken.
            raise AFSBrokenDirectoryError(
                f"in-use list has at least {len(results)} entries but DRENTS says {expected_count}"
            )

    if len(results) != expected_count:
        raise AFSBrokenDirectoryError(
            f"in-use list length {len(results)} disagrees with DRENTS {expected_count}"
        )

    return results


def _parse_slot(data: bytes, slot_offset: int) -> tuple[DirectoryEntry, int]:
    """Parse one 26-byte entry slot at byte offset ``slot_offset``.

    Returns (entry, next_pointer).
    """
    if slot_offset + ENTRY_SIZE > len(data):
        raise AFSBrokenDirectoryError(
            f"entry at offset {slot_offset:#x} extends past directory size"
        )
    slot = data[slot_offset : slot_offset + ENTRY_SIZE]

    next_pointer = int.from_bytes(slot[_ENT_OFF_LINK : _ENT_OFF_LINK + 2], "little")

    try:
        name = _decode_name(bytes(slot[_ENT_OFF_NAME : _ENT_OFF_NAME + MAX_NAME_LENGTH]))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AFSBrokenDirectoryError(f"bad entry name at offset {slot_offset:#x}: {exc}") from exc

    load_address = int.from_bytes(slot[_ENT_OFF_LOAD : _ENT_OFF_LOAD + 4], "little")
    exec_address = int.from_bytes(slot[_ENT_OFF_EXEC : _ENT_OFF_EXEC + 4], "little")
    access = AFSAccess.from_byte(slot[_ENT_OFF_ACCESS])

    try:
        date = AfsDate.from_bytes(bytes(slot[_ENT_OFF_DATE : _ENT_OFF_DATE + 2]))
    except ValueError as exc:
        raise AFSBrokenDirectoryError(f"bad entry date at offset {slot_offset:#x}: {exc}") from exc

    sin = SystemInternalName(int.from_bytes(slot[_ENT_OFF_SIN : _ENT_OFF_SIN + 3], "little"))

    entry = DirectoryEntry(
        name=name,
        load_address=load_address,
        exec_address=exec_address,
        access=access,
        date=date,
        sin=sin,
    )
    return entry, next_pointer


# ---------------------------------------------------------------------------
# Builder — used by tests to construct directory bytes without going
# through a write path (which doesn't exist yet in phase 5).
# ---------------------------------------------------------------------------


def build_directory_bytes(
    name: str,
    master_sequence_number: int,
    entries: list[DirectoryEntry],
    size_in_bytes: int,
) -> bytes:
    """Serialise a directory for test use.

    Populates the slot array from the end backwards (matching the
    server's behaviour), threads the in-use list in alphabetical
    order (by ``name.upper()``), and chains the free list through
    the unused slots from the beginning forward.

    Phase 5 uses this only to build test fixtures. The real write
    path in phase 9 will handle insertion/deletion incrementally
    against a live directory and will produce the same on-disc shape.
    """
    if size_in_bytes < MIN_DIRECTORY_SIZE:
        raise ValueError(f"directory size {size_in_bytes} below minimum {MIN_DIRECTORY_SIZE}")
    if size_in_bytes % 256 != 0:
        raise ValueError(f"directory size {size_in_bytes} must be a multiple of 256")

    capacity = min(
        (size_in_bytes - HEADER_SIZE - TRAILING_SEQ_SIZE) // ENTRY_SIZE,
        MAX_ENTRIES,
    )
    if len(entries) > capacity:
        raise ValueError(
            f"cannot fit {len(entries)} entries in a directory with capacity {capacity}"
        )

    sorted_entries = sorted(entries, key=lambda e: e.name.upper())

    buf = bytearray(size_in_bytes)
    buf[_OFF_MASTER_SEQ] = master_sequence_number
    buf[_OFF_NAME : _OFF_NAME + MAX_NAME_LENGTH] = _encode_name(name)
    buf[_OFF_NUM_ENTRIES : _OFF_NUM_ENTRIES + 2] = len(sorted_entries).to_bytes(2, "little")
    buf[size_in_bytes - 1] = master_sequence_number

    def slot_pointer(slot_index: int) -> int:
        return HEADER_SIZE + slot_index * ENTRY_SIZE

    # Place entries in the highest-numbered slots, matching WFSINIT /
    # file server behaviour. Slot ``capacity-1`` gets the first (by
    # name) in-use entry, slot ``capacity-2`` the second, etc.
    slot_index_for_entry: list[int] = []
    for i, entry in enumerate(sorted_entries):
        slot_idx = capacity - 1 - i
        slot_index_for_entry.append(slot_idx)
        offset = slot_pointer(slot_idx)
        slot = bytearray(ENTRY_SIZE)
        slot[_ENT_OFF_NAME : _ENT_OFF_NAME + MAX_NAME_LENGTH] = _encode_name(entry.name)
        slot[_ENT_OFF_LOAD : _ENT_OFF_LOAD + 4] = entry.load_address.to_bytes(4, "little")
        slot[_ENT_OFF_EXEC : _ENT_OFF_EXEC + 4] = entry.exec_address.to_bytes(4, "little")
        slot[_ENT_OFF_ACCESS] = entry.access.to_byte()
        slot[_ENT_OFF_DATE : _ENT_OFF_DATE + 2] = entry.date.to_bytes()
        slot[_ENT_OFF_SIN : _ENT_OFF_SIN + 3] = int(entry.sin).to_bytes(3, "little")
        buf[offset : offset + ENTRY_SIZE] = slot

    # Thread the in-use linked list: DRFRST → first entry's slot →
    # ... → last entry's slot, with next pointer = 0.
    if sorted_entries:
        first_slot_offset = slot_pointer(slot_index_for_entry[0])
        buf[_OFF_FIRST_POINTER : _OFF_FIRST_POINTER + 2] = first_slot_offset.to_bytes(2, "little")
        for i in range(len(sorted_entries) - 1):
            src_off = slot_pointer(slot_index_for_entry[i])
            next_off = slot_pointer(slot_index_for_entry[i + 1])
            buf[src_off + _ENT_OFF_LINK : src_off + _ENT_OFF_LINK + 2] = next_off.to_bytes(
                2, "little"
            )
        # Last entry's link stays 0 (end of list).
    else:
        buf[_OFF_FIRST_POINTER : _OFF_FIRST_POINTER + 2] = (0).to_bytes(2, "little")

    # Thread the free list: walk through the unused slot indices in
    # ascending order (so the first free slot is the lowest-numbered
    # one, matching where the server would place the next created
    # entry).
    used_slot_indices = set(slot_index_for_entry)
    free_slots = [i for i in range(capacity) if i not in used_slot_indices]

    if free_slots:
        first_free_off = slot_pointer(free_slots[0])
        buf[_OFF_FREE_POINTER : _OFF_FREE_POINTER + 2] = first_free_off.to_bytes(2, "little")
        for i in range(len(free_slots) - 1):
            src_off = slot_pointer(free_slots[i])
            next_off = slot_pointer(free_slots[i + 1])
            buf[src_off + _ENT_OFF_LINK : src_off + _ENT_OFF_LINK + 2] = next_off.to_bytes(
                2, "little"
            )
        # Last free slot has link = 0 (end of free list).
    else:
        buf[_OFF_FREE_POINTER : _OFF_FREE_POINTER + 2] = (0).to_bytes(2, "little")

    return bytes(buf)

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
from oaknut.afs.exceptions import (
    AFSBrokenDirectoryError,
    AFSDirectoryEntryExistsError,
    AFSDirectoryEntryNotFoundError,
    AFSDirectoryFullError,
)
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

    # Thread the free list: WFSINIT's PROCmake_dir (line 2730-2750)
    # sets freep = highest slot offset and chains each slot's next
    # pointer to the slot below it, ending at 0. This means
    # entries are popped from the highest free slot first, which
    # matches the in-use placement above (highest slots for the
    # first entries by name).
    used_slot_indices = set(slot_index_for_entry)
    free_slots = [i for i in range(capacity) if i not in used_slot_indices]

    if free_slots:
        # Head is the highest-indexed free slot.
        first_free_off = slot_pointer(free_slots[-1])
        buf[_OFF_FREE_POINTER : _OFF_FREE_POINTER + 2] = first_free_off.to_bytes(2, "little")
        # Chain from high to low: each slot points to the one below.
        for i in range(len(free_slots) - 1, 0, -1):
            src_off = slot_pointer(free_slots[i])
            next_off = slot_pointer(free_slots[i - 1])
            buf[src_off + _ENT_OFF_LINK : src_off + _ENT_OFF_LINK + 2] = next_off.to_bytes(
                2, "little"
            )
        # Lowest free slot has link = 0 (end of free list).
    else:
        buf[_OFF_FREE_POINTER : _OFF_FREE_POINTER + 2] = (0).to_bytes(2, "little")

    return bytes(buf)


# ---------------------------------------------------------------------------
# Byte-level mutation — phase 9: insert / delete / rename / update
# ---------------------------------------------------------------------------
#
# These operate on the raw on-disc bytes of a directory object, not on
# a parsed :class:`AfsDirectory`, because the physical slot layout
# matters for ROM-compatible behaviour and round-tripping. The parsed
# form erases slot positions and free-list ordering.
#
# Each function mirrors the corresponding DIRMAN routine:
#
# - :func:`insert_entry` — RETANP path at ``Uade0E.asm:789-944``.
#   Pops the free-list head, rewrites the new slot's content, splices
#   it into the in-use list at alphabetic position using the same
#   insertion-point logic as ``FNDTEX`` (``Uade0D.asm:220-250``).
# - :func:`delete_entry` — DRDELT at ``Uade0C.asm:330-397``. Walks the
#   in-use list to the named entry, unlinks it from the in-use chain,
#   prepends the freed slot to the free list (``FREECH`` at
#   ``Uade0D.asm:1297``) LIFO-style.
# - :func:`rename_entry` — RETANB path at ``Uade0E.asm:806-851``.
#   Rewrites the ``DRTITL`` field in place without re-threading the
#   in-use list. **This can leave the list un-sorted** if the rename
#   crosses a neighbouring entry's name; the ROM accepts this and
#   ``FNDTEX`` on the resulting directory may fail to locate entries
#   whose sort position is past the rename point until the directory
#   is next rebuilt.
# - :func:`update_entry_fields` — the duplicate-insert replace path
#   at ``Uade0E.asm:850``. Rewrites load/exec/date in place without
#   touching the name, access byte, or list threading.
#
# All four functions bump the leading and trailing master-sequence
# bytes (``ENSRIT`` semantics from ``Uade0D.asm:815``). Every
# successful mutation produces bytes whose leading ``DRSQNO`` byte is
# ``(old + 1) & 0xFF`` and whose final byte matches.

# ---------------------------------------------------------------------------
# Low-level byte-buffer helpers
# ---------------------------------------------------------------------------


def _header_first_pointer(buf: bytes | bytearray) -> int:
    return int.from_bytes(buf[_OFF_FIRST_POINTER : _OFF_FIRST_POINTER + 2], "little")


def _header_free_pointer(buf: bytes | bytearray) -> int:
    return int.from_bytes(buf[_OFF_FREE_POINTER : _OFF_FREE_POINTER + 2], "little")


def _header_num_entries(buf: bytes | bytearray) -> int:
    return int.from_bytes(buf[_OFF_NUM_ENTRIES : _OFF_NUM_ENTRIES + 2], "little")


def _set_first_pointer(buf: bytearray, value: int) -> None:
    buf[_OFF_FIRST_POINTER : _OFF_FIRST_POINTER + 2] = value.to_bytes(2, "little")


def _set_free_pointer(buf: bytearray, value: int) -> None:
    buf[_OFF_FREE_POINTER : _OFF_FREE_POINTER + 2] = value.to_bytes(2, "little")


def _set_num_entries(buf: bytearray, value: int) -> None:
    buf[_OFF_NUM_ENTRIES : _OFF_NUM_ENTRIES + 2] = value.to_bytes(2, "little")


def _slot_link(buf: bytes | bytearray, slot_offset: int) -> int:
    return int.from_bytes(
        buf[slot_offset + _ENT_OFF_LINK : slot_offset + _ENT_OFF_LINK + 2], "little"
    )


def _set_slot_link(buf: bytearray, slot_offset: int, value: int) -> None:
    buf[slot_offset + _ENT_OFF_LINK : slot_offset + _ENT_OFF_LINK + 2] = value.to_bytes(2, "little")


def _slot_name(buf: bytes | bytearray, slot_offset: int) -> str:
    raw = bytes(buf[slot_offset + _ENT_OFF_NAME : slot_offset + _ENT_OFF_NAME + MAX_NAME_LENGTH])
    return raw.rstrip(b" \x00").decode("ascii")


def _bump_sequence(buf: bytearray) -> int:
    """Increment both the leading and trailing master-sequence bytes.

    Matches ``ENSRIT`` at ``Uade0D.asm:815``: two pointer rewrites
    (leading at offset ``DRSQNO = 2``, trailing at the directory's
    last byte), wrapping through 0xFF→0x00. Returns the new value.
    """
    new_seq = (buf[_OFF_MASTER_SEQ] + 1) & 0xFF
    buf[_OFF_MASTER_SEQ] = new_seq
    buf[-1] = new_seq
    return new_seq


def _write_entry_payload(
    buf: bytearray,
    slot_offset: int,
    entry: DirectoryEntry,
) -> None:
    """Overwrite the payload fields (name through SIN) of a slot.

    Leaves the ``DRLINK`` field untouched — the caller is responsible
    for threading the slot into whichever list it belongs to.
    """
    buf[slot_offset + _ENT_OFF_NAME : slot_offset + _ENT_OFF_NAME + MAX_NAME_LENGTH] = _encode_name(
        entry.name
    )
    buf[slot_offset + _ENT_OFF_LOAD : slot_offset + _ENT_OFF_LOAD + 4] = (
        entry.load_address.to_bytes(4, "little")
    )
    buf[slot_offset + _ENT_OFF_EXEC : slot_offset + _ENT_OFF_EXEC + 4] = (
        entry.exec_address.to_bytes(4, "little")
    )
    buf[slot_offset + _ENT_OFF_ACCESS] = entry.access.to_byte()
    buf[slot_offset + _ENT_OFF_DATE : slot_offset + _ENT_OFF_DATE + 2] = entry.date.to_bytes()
    buf[slot_offset + _ENT_OFF_SIN : slot_offset + _ENT_OFF_SIN + 3] = int(entry.sin).to_bytes(
        3, "little"
    )


def _find_in_use_insertion_point(
    buf: bytes | bytearray,
    new_name: str,
) -> tuple[int, int | None]:
    """Walk the in-use list looking for the alphabetic insertion point.

    Returns ``(predecessor_link_offset, successor_slot_offset)`` where:

    - ``predecessor_link_offset`` is the byte offset of the 16-bit
      ``DRLINK`` (or ``DRFRST``) field that currently holds the
      pointer which should be rewritten to point at the new slot.
    - ``successor_slot_offset`` is the offset of the existing entry
      that should become the new slot's successor (i.e. the value
      currently stored at ``predecessor_link_offset``), or ``None``
      if the new entry will be appended at the end of the list.

    If a duplicate name is encountered the walk raises
    :class:`AFSDirectoryEntryExistsError` — the ROM's RETANB path
    replaces in place, but our public :func:`insert_entry` refuses
    duplicates and surfaces a clear error instead. Use
    :func:`update_entry_fields` if you want the ROM's overwrite
    semantics.
    """
    new_name_upper = new_name.upper()
    pred_link_offset = _OFF_FIRST_POINTER  # header's DRFRST is the "predecessor link"
    current_slot = _header_first_pointer(buf)

    while current_slot != 0:
        current_name = _slot_name(buf, current_slot)
        current_upper = current_name.upper()
        if current_upper == new_name_upper:
            raise AFSDirectoryEntryExistsError(
                f"directory already contains an entry named {current_name!r}"
            )
        if new_name_upper < current_upper:
            return pred_link_offset, current_slot
        pred_link_offset = current_slot + _ENT_OFF_LINK
        current_slot = _slot_link(buf, current_slot)

    return pred_link_offset, None


def _find_in_use_entry(
    buf: bytes | bytearray,
    name: str,
) -> tuple[int, int]:
    """Walk the in-use list looking for ``name``.

    Returns ``(predecessor_link_offset, slot_offset)`` where
    ``slot_offset`` is the offset of the matching entry and
    ``predecessor_link_offset`` is the offset of the 16-bit field
    whose current value is ``slot_offset`` (either the header's
    ``DRFRST`` or the predecessor slot's ``DRLINK``). This is the
    pointer the delete path rewrites to unlink the matched slot.

    Raises :class:`AFSDirectoryEntryNotFoundError` if the walk hits
    the end of the list without finding a match.
    """
    target_upper = name.upper()
    pred_link_offset = _OFF_FIRST_POINTER
    current_slot = _header_first_pointer(buf)

    while current_slot != 0:
        current_name = _slot_name(buf, current_slot)
        if current_name.upper() == target_upper:
            return pred_link_offset, current_slot
        pred_link_offset = current_slot + _ENT_OFF_LINK
        current_slot = _slot_link(buf, current_slot)

    raise AFSDirectoryEntryNotFoundError(f"no entry named {name!r} in the directory")


# ---------------------------------------------------------------------------
# Public mutation API
# ---------------------------------------------------------------------------


def insert_entry(raw: bytes, entry: DirectoryEntry) -> bytes:
    """Return new directory bytes with ``entry`` inserted.

    Follows the DIRMAN insertion algorithm:

    1. Pop the head of the free list (``DRFREE``). If the free list
       is empty, raise :class:`AFSDirectoryFullError` — phase 10 will
       add automatic growth to match the ROM.
    2. Walk the in-use list to the first entry whose name is greater
       than ``entry.name``; this is the insertion point. If a
       duplicate name is encountered, raise
       :class:`AFSDirectoryEntryExistsError`.
    3. Write the new entry's payload into the popped slot and splice
       it into the in-use list between the predecessor and successor.
    4. Increment ``DRENTS`` and bump the master sequence number
       (both leading and trailing copies).
    """
    buf = bytearray(raw)

    free_head = _header_free_pointer(buf)
    if free_head == 0:
        raise AFSDirectoryFullError(
            "directory has no free slots (capacity reached); phase 10 will auto-grow"
        )

    # Step 2 is done first so we can reject duplicates without touching
    # the free list at all.
    pred_link_offset, successor = _find_in_use_insertion_point(buf, entry.name)

    # Step 1: pop free-list head.
    new_slot_offset = free_head
    next_free = _slot_link(buf, new_slot_offset)
    _set_free_pointer(buf, next_free)

    # Step 3: write the payload + splice.
    _write_entry_payload(buf, new_slot_offset, entry)
    # The new slot's next-link points at the successor (which may be
    # 0 if the insertion is at the end of the list).
    _set_slot_link(buf, new_slot_offset, successor or 0)
    # The predecessor's next-link now points at our new slot.
    if pred_link_offset == _OFF_FIRST_POINTER:
        _set_first_pointer(buf, new_slot_offset)
    else:
        buf[pred_link_offset : pred_link_offset + 2] = new_slot_offset.to_bytes(2, "little")

    # Step 4: count and sequence.
    _set_num_entries(buf, _header_num_entries(buf) + 1)
    _bump_sequence(buf)
    return bytes(buf)


def delete_entry(raw: bytes, name: str) -> bytes:
    """Return new directory bytes with ``name`` removed.

    Raises :class:`AFSDirectoryEntryNotFoundError` if no entry with
    that name exists. **Does not check for access-byte locked / open
    file / non-empty-directory** — those checks belong at the higher
    AFS layer (``DELCHK`` at ``Uade0D:1191`` in the ROM), where the
    caller has enough context to consult the file's access byte and
    walk the sub-directory if needed.

    The deletion:

    1. Walks the in-use list to find the entry, returning the
       offset of the predecessor's link field.
    2. Rewrites the predecessor's link to skip over the entry
       (unlink from in-use list).
    3. Prepends the freed slot to the free list (LIFO — see
       ``FREECH`` at ``Uade0D:1297``).
    4. Decrements ``DRENTS`` and bumps the sequence number.
    """
    buf = bytearray(raw)

    pred_link_offset, slot_offset = _find_in_use_entry(buf, name)

    # Step 2: splice the entry out of the in-use list.
    successor = _slot_link(buf, slot_offset)
    if pred_link_offset == _OFF_FIRST_POINTER:
        _set_first_pointer(buf, successor)
    else:
        buf[pred_link_offset : pred_link_offset + 2] = successor.to_bytes(2, "little")

    # Step 3: prepend to free list. New free-list head = the slot we
    # just freed; its next-link is the previous head.
    old_free_head = _header_free_pointer(buf)
    _set_slot_link(buf, slot_offset, old_free_head)
    _set_free_pointer(buf, slot_offset)

    # Step 4: count and sequence.
    _set_num_entries(buf, _header_num_entries(buf) - 1)
    _bump_sequence(buf)
    return bytes(buf)


def rename_entry(raw: bytes, old_name: str, new_name: str) -> bytes:
    """Return new directory bytes with ``old_name`` renamed to ``new_name``.

    Matches the ROM's in-place rename semantics: the slot's
    ``DRTITL`` field is overwritten but the in-use list is **not**
    re-threaded. If ``new_name`` would sort to a different position,
    the list becomes un-ordered. Subsequent ``FNDTEX`` walks may
    then fail to locate entries whose sort position is past the
    rename point, just as they would on a ROM-managed directory.

    Implementations that need a sorted result can delete+reinsert
    instead. The ``AFSPath.rename`` helper higher up will do that
    automatically when it crosses a directory boundary, but
    same-directory in-place rename is retained for byte-exact
    compatibility with the ROM.

    Raises :class:`AFSDirectoryEntryNotFoundError` if ``old_name``
    is missing, and :class:`AFSDirectoryEntryExistsError` if
    ``new_name`` already exists under a different slot.
    """
    if old_name == new_name:
        # No-op, but still bumps the sequence number like the ROM
        # would if ENSRIT is called — we treat this as a deliberate
        # touch.
        buf = bytearray(raw)
        # Verify the name exists first.
        _find_in_use_entry(buf, old_name)
        _bump_sequence(buf)
        return bytes(buf)

    buf = bytearray(raw)
    _, slot_offset = _find_in_use_entry(buf, old_name)

    # Check the destination name doesn't already exist in a
    # different slot.
    try:
        _, conflicting = _find_in_use_entry(buf, new_name)
    except AFSDirectoryEntryNotFoundError:
        pass
    else:
        if conflicting != slot_offset:
            raise AFSDirectoryEntryExistsError(
                f"directory already contains an entry named {new_name!r}"
            )

    buf[slot_offset + _ENT_OFF_NAME : slot_offset + _ENT_OFF_NAME + MAX_NAME_LENGTH] = _encode_name(
        new_name
    )
    _bump_sequence(buf)
    return bytes(buf)


def update_entry_fields(
    raw: bytes,
    name: str,
    *,
    load_address: int | None = None,
    exec_address: int | None = None,
    access: AFSAccess | None = None,
    date: AfsDate | None = None,
    sin: SystemInternalName | None = None,
) -> bytes:
    """Return new directory bytes with selected fields of ``name`` updated.

    By default this leaves the ``name`` and ``access`` fields
    untouched — matching the ROM's RETANB replace path at
    ``Uade0E.asm:850``, which preserves the access byte when an
    insert collides with an existing entry.  Callers who explicitly
    want to rewrite the access byte (``AFSPath.chmod`` and friends)
    can pass ``access=...``.  Any subset of ``load_address`` /
    ``exec_address`` / ``access`` / ``date`` / ``sin`` may be
    ``None`` to leave that field alone.

    Raises :class:`AFSDirectoryEntryNotFoundError` if ``name``
    does not exist.
    """
    buf = bytearray(raw)
    _, slot_offset = _find_in_use_entry(buf, name)

    if load_address is not None:
        if not (0 <= load_address <= 0xFFFFFFFF):
            raise ValueError(f"load_address {load_address} outside 0..0xFFFFFFFF")
        buf[slot_offset + _ENT_OFF_LOAD : slot_offset + _ENT_OFF_LOAD + 4] = load_address.to_bytes(
            4, "little"
        )
    if exec_address is not None:
        if not (0 <= exec_address <= 0xFFFFFFFF):
            raise ValueError(f"exec_address {exec_address} outside 0..0xFFFFFFFF")
        buf[slot_offset + _ENT_OFF_EXEC : slot_offset + _ENT_OFF_EXEC + 4] = exec_address.to_bytes(
            4, "little"
        )
    if access is not None:
        buf[slot_offset + _ENT_OFF_ACCESS] = access.to_byte()
    if date is not None:
        buf[slot_offset + _ENT_OFF_DATE : slot_offset + _ENT_OFF_DATE + 2] = date.to_bytes()
    if sin is not None:
        if not (0 <= int(sin) <= 0xFFFFFF):
            raise ValueError(f"sin {sin} outside 0..0xFFFFFF")
        buf[slot_offset + _ENT_OFF_SIN : slot_offset + _ENT_OFF_SIN + 3] = int(sin).to_bytes(
            3, "little"
        )

    _bump_sequence(buf)
    return bytes(buf)


# ---------------------------------------------------------------------------
# Directory growth — phase 10
# ---------------------------------------------------------------------------
#
# Mirrors the DIRMAN ``CHZSZE`` → ``FORMAT`` flow (Uade0E:1206-). The
# allocator half of growth (extending the underlying object's map
# chain by one more sector) is the caller's responsibility; this
# function takes the already-extended raw bytes and threads the new
# slot grid onto the free list. The trailing sequence byte moves to
# the new last byte. Both leading and trailing sequence bytes are
# bumped.
#
# Unlike the ROM, the Python path does not shrink back to the
# tightest whole-block size (FORMTM's second MAPMAN.CHANGESIZE call)
# — the result may carry up to 25 bytes of padding at the tail.
# Phase 20's byte-exact wfsinit_compat mode can revisit if needed.


def grow_directory_bytes(raw: bytes, new_size_bytes: int) -> bytes:
    """Return the directory bytes extended to ``new_size_bytes``.

    ``raw`` must be the bytes of a valid directory smaller than
    ``new_size_bytes``. The tail is zero-extended, new slots from
    the extended region are prepended onto the free list LIFO-style,
    and the trailing sequence byte is written at the new last byte.
    The leading + trailing master sequence number is bumped.

    Raises :class:`ValueError` if ``new_size_bytes`` is not strictly
    larger than the current size, not a multiple of 256, or would
    add zero usable slots.
    """
    old_size = len(raw)
    if new_size_bytes <= old_size:
        raise ValueError(f"new_size_bytes ({new_size_bytes}) must exceed current size ({old_size})")
    if new_size_bytes % 256 != 0:
        raise ValueError(f"new_size_bytes ({new_size_bytes}) must be a multiple of 256")

    old_capacity = (old_size - HEADER_SIZE - TRAILING_SEQ_SIZE) // ENTRY_SIZE
    if old_capacity > MAX_ENTRIES:
        old_capacity = MAX_ENTRIES
    new_capacity = (new_size_bytes - HEADER_SIZE - TRAILING_SEQ_SIZE) // ENTRY_SIZE
    if new_capacity > MAX_ENTRIES:
        new_capacity = MAX_ENTRIES
    if new_capacity <= old_capacity:
        raise ValueError(
            f"grow from {old_size} to {new_size_bytes} bytes does not add any slots "
            f"(old_capacity={old_capacity}, new_capacity={new_capacity})"
        )

    buf = bytearray(new_size_bytes)
    buf[:old_size] = raw

    for slot_index in range(old_capacity, new_capacity):
        slot_offset = HEADER_SIZE + slot_index * ENTRY_SIZE
        # Zero the slot so the parser's name/date checks can't trip
        # on stale bytes from the just-allocated tail sector.
        buf[slot_offset : slot_offset + ENTRY_SIZE] = b"\x00" * ENTRY_SIZE
        old_free_head = _header_free_pointer(buf)
        _set_slot_link(buf, slot_offset, old_free_head)
        _set_free_pointer(buf, slot_offset)

    # Trailing sequence byte moves to the new last byte.
    buf[-1] = buf[_OFF_MASTER_SEQ]
    _bump_sequence(buf)

    return bytes(buf)

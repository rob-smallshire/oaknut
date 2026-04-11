"""AFS passwords file — read-only side.

The passwords file is an ordinary AFS object named ``$.Passwords``
with access byte ``&00`` (no owner or public access). Its contents
are a flat concatenation of 31-byte entries — no header, no
identifier — one per user. The number of entries is derived from
the file length.

Layout of each 31-byte entry (``PWENSZ``, from ``Uade02.asm:177-200``):

======  ====  ==========================================================
Offset  Size  Meaning
======  ====  ==========================================================
 0-19    20   ``PWUSID`` — user ID (up to ``MAXUNM-1 = 20`` chars).
              Either ``user`` or ``group.user`` with a dot separator.
              Terminated with CR (``&0D``) if shorter.
  20-25   6   ``PWPASS`` — password (up to ``MAXPW = 6`` chars).
              CR-terminated if shorter.
  26-29   4   ``PWFREE`` — free-space quota remaining (32-bit LE).
     30   1   ``PWFLAG`` — status byte; see :class:`StatusByte`.
======  ====  ==========================================================

The status byte layout (``Uade01.asm:263-268``):

======  =========================================================
Bit     Meaning
======  =========================================================
 0-1    Boot option (0 = off, 1 = load, 2 = run, 3 = exec)
 2-4    Unused
   5    ``LOCKPV`` — lock user privileges
   6    ``SYSTPV`` — system privilege
   7    ``INUSE`` — entry is in use (clear = ignored slot)
======  =========================================================

Phase 6 implements the read side only: parse a bytes image of the
passwords file and expose a read-only view of its :class:`UserRecord`
entries. Mutation, quota admin, and permission checks come in phase 14.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from oaknut.file import BootOption

# ---------------------------------------------------------------------------
# Constants — names match the L3V126 ROM symbols.
# ---------------------------------------------------------------------------

ENTRY_SIZE = 31  # PWENSZ
_OFF_USER_ID = 0
_LEN_USER_ID = 20  # MAXUNM - 1
_OFF_PASSWORD = 20
_LEN_PASSWORD = 6  # MAXPW
_OFF_FREE_SPACE = 26
_LEN_FREE_SPACE = 4  # UTFRLN
_OFF_STATUS = 30

# Status byte bit masks
BOOT_MASK = 0x03  # bits 0-1
LOCKPV = 0x20  # bit 5
SYSTPV = 0x40  # bit 6
INUSE = 0x80  # bit 7

_CR = 0x0D  # terminator used inside PWUSID / PWPASS when shorter than field

#: WFSINIT creates the passwords file with an initial capacity of one
#: sector (~8 entries). Later phases grow it as users are added.
PASSWORDS_FILENAME = "Passwords"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_cr_terminated(raw: bytes) -> str:
    """Decode a CR-terminated, zero-padded ASCII field."""
    end = raw.find(bytes((_CR,)))
    if end == -1:
        end = len(raw)
        # Strip any trailing NULs / spaces the producer may have left.
        trimmed = raw[:end].rstrip(b"\x00 ")
        return trimmed.decode("ascii", errors="replace")
    return raw[:end].decode("ascii", errors="replace")


# ---------------------------------------------------------------------------
# UserRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UserRecord:
    """A single parsed passwords file entry.

    ``name`` is the bare user name (the portion after ``group.`` if
    the user belongs to a group) and ``group`` is the group prefix
    or ``None``. The two together form the ``PWUSID`` field.

    Phase 6 parses and exposes; phase 14 will introduce the mutating
    operations (add, remove, set_quota, set_password, etc.).
    """

    name: str
    group: str | None
    password: str
    free_space: int
    is_in_use: bool
    is_system: bool
    is_privileges_locked: bool
    boot_option: BootOption

    @property
    def full_id(self) -> str:
        """The ``group.user`` or ``user`` form as stored on disc."""
        if self.group is None:
            return self.name
        return f"{self.group}.{self.name}"

    @classmethod
    def from_bytes(cls, entry: bytes) -> UserRecord:
        if len(entry) != ENTRY_SIZE:
            raise ValueError(f"passwords entry must be {ENTRY_SIZE} bytes, got {len(entry)}")

        user_id = _decode_cr_terminated(entry[_OFF_USER_ID : _OFF_USER_ID + _LEN_USER_ID])
        password = _decode_cr_terminated(entry[_OFF_PASSWORD : _OFF_PASSWORD + _LEN_PASSWORD])
        free_space = int.from_bytes(
            entry[_OFF_FREE_SPACE : _OFF_FREE_SPACE + _LEN_FREE_SPACE], "little"
        )
        status = entry[_OFF_STATUS]

        if "." in user_id:
            group, _, name = user_id.partition(".")
        else:
            group = None
            name = user_id

        return cls(
            name=name,
            group=group,
            password=password,
            free_space=free_space,
            is_in_use=bool(status & INUSE),
            is_system=bool(status & SYSTPV),
            is_privileges_locked=bool(status & LOCKPV),
            boot_option=BootOption(status & BOOT_MASK),
        )


# ---------------------------------------------------------------------------
# PasswordsFile
# ---------------------------------------------------------------------------


class PasswordsFile(Sequence[UserRecord]):
    """Read-only view over the parsed ``$.Passwords`` entries.

    Supports iteration (all slots, including the ``!is_in_use``
    tombstones from deleted users), length, integer indexing, and
    name-based lookup via ``__getitem__(str)`` or :meth:`find`.
    Only in-use entries are considered for name lookup; stale slots
    are skipped.

    Mutation arrives in phase 14. Until then this class intentionally
    exposes no write surface so that the read path can ship cleanly.
    """

    def __init__(self, records: Sequence[UserRecord]) -> None:
        self._records: tuple[UserRecord, ...] = tuple(records)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> PasswordsFile:
        """Parse a passwords file image.

        The server requires the file to be a whole number of sectors;
        we tolerate any length that is a multiple of ``ENTRY_SIZE``.
        """
        if len(data) % ENTRY_SIZE != 0:
            raise ValueError(
                f"passwords file length {len(data)} is not a multiple of {ENTRY_SIZE}"
            )
        records = [
            UserRecord.from_bytes(bytes(data[offset : offset + ENTRY_SIZE]))
            for offset in range(0, len(data), ENTRY_SIZE)
        ]
        return cls(records)

    # ------------------------------------------------------------------
    # Sequence protocol — includes tombstoned slots
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._records)

    def __getitem__(self, key):  # type: ignore[override]
        if isinstance(key, str):
            return self.find(key)
        return self._records[key]

    def __iter__(self) -> Iterator[UserRecord]:
        return iter(self._records)

    # ------------------------------------------------------------------
    # Active-user convenience
    # ------------------------------------------------------------------

    @property
    def active(self) -> tuple[UserRecord, ...]:
        """All in-use records, in disc order."""
        return tuple(r for r in self._records if r.is_in_use)

    def find(self, name: str) -> UserRecord:
        """Look up an in-use entry by its bare or ``group.user`` ID.

        Case-insensitive (the file server compares user IDs
        case-insensitively per ``Uade06``). Raises :class:`KeyError`
        if no active entry matches.
        """
        target = name.upper()
        for record in self._records:
            if not record.is_in_use:
                continue
            if record.full_id.upper() == target or record.name.upper() == target:
                return record
        raise KeyError(f"no user named {name!r} in passwords file")

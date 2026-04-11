"""Unit tests for ``oaknut.afs.passwords`` — read path."""

from __future__ import annotations

import pytest
from oaknut.afs import PasswordsFile, UserRecord
from oaknut.afs.passwords import (
    BOOT_MASK,
    ENTRY_SIZE,
    INUSE,
    LOCKPV,
    SYSTPV,
)
from oaknut.file import BootOption


def _entry(
    user_id: str,
    password: str = "",
    *,
    free_space: int = 0,
    status: int = INUSE,
) -> bytes:
    raw = bytearray(ENTRY_SIZE)
    uid_bytes = user_id.encode("ascii")
    raw[: len(uid_bytes)] = uid_bytes
    if len(uid_bytes) < 20:
        raw[len(uid_bytes)] = 0x0D
    pwd_bytes = password.encode("ascii")
    raw[20 : 20 + len(pwd_bytes)] = pwd_bytes
    if len(pwd_bytes) < 6:
        raw[20 + len(pwd_bytes)] = 0x0D
    raw[26:30] = free_space.to_bytes(4, "little")
    raw[30] = status
    return bytes(raw)


class TestUserRecordFromBytes:
    def test_bare_user(self) -> None:
        record = UserRecord.from_bytes(_entry("alice"))
        assert record.name == "alice"
        assert record.group is None
        assert record.full_id == "alice"

    def test_group_user(self) -> None:
        record = UserRecord.from_bytes(_entry("dept.bob"))
        assert record.group == "dept"
        assert record.name == "bob"
        assert record.full_id == "dept.bob"

    def test_free_space_decoded(self) -> None:
        record = UserRecord.from_bytes(_entry("carol", free_space=0x123456))
        assert record.free_space == 0x123456

    def test_password_decoded(self) -> None:
        record = UserRecord.from_bytes(_entry("dave", password="pass"))
        assert record.password == "pass"

    def test_in_use_flag(self) -> None:
        assert UserRecord.from_bytes(_entry("a", status=INUSE)).is_in_use
        assert not UserRecord.from_bytes(_entry("a", status=0)).is_in_use

    def test_system_flag(self) -> None:
        record = UserRecord.from_bytes(_entry("root", status=INUSE | SYSTPV))
        assert record.is_system

    def test_privileges_locked(self) -> None:
        record = UserRecord.from_bytes(_entry("x", status=INUSE | LOCKPV))
        assert record.is_privileges_locked

    def test_boot_option_run(self) -> None:
        record = UserRecord.from_bytes(_entry("x", status=INUSE | int(BootOption.RUN)))
        assert record.boot_option == BootOption.RUN

    def test_boot_option_exec(self) -> None:
        record = UserRecord.from_bytes(_entry("x", status=INUSE | int(BootOption.EXEC)))
        assert record.boot_option == BootOption.EXEC

    def test_all_boot_option_values_round_trip(self) -> None:
        for opt in BootOption:
            record = UserRecord.from_bytes(_entry("u", status=INUSE | int(opt)))
            assert record.boot_option == opt

    def test_wrong_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="31 bytes"):
            UserRecord.from_bytes(b"\x00" * 30)


class TestPasswordsFileParse:
    def test_empty_file(self) -> None:
        passwords = PasswordsFile.from_bytes(b"")
        assert len(passwords) == 0
        assert list(passwords) == []

    def test_two_entries(self) -> None:
        data = _entry("alice", status=INUSE) + _entry("bob", status=INUSE)
        passwords = PasswordsFile.from_bytes(data)
        assert len(passwords) == 2

    def test_active_excludes_tombstones(self) -> None:
        data = _entry("alive", status=INUSE) + _entry("dead", status=0)
        passwords = PasswordsFile.from_bytes(data)
        assert {u.name for u in passwords.active} == {"alive"}

    def test_find_case_insensitive(self) -> None:
        data = _entry("AliCe", status=INUSE)
        passwords = PasswordsFile.from_bytes(data)
        assert passwords.find("alice").name == "AliCe"

    def test_find_rejects_tombstone(self) -> None:
        data = _entry("alice", status=0)  # !INUSE
        passwords = PasswordsFile.from_bytes(data)
        with pytest.raises(KeyError):
            passwords.find("alice")

    def test_non_multiple_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="multiple"):
            PasswordsFile.from_bytes(b"\x00" * (ENTRY_SIZE + 1))

    def test_boot_mask_is_two_bits(self) -> None:
        assert BOOT_MASK == 0b11

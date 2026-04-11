"""Phase 14 — mutating the PasswordsFile.

These tests drive the pure bytes⇄records mutation surface on
:class:`PasswordsFile`. They do not write through an AFS handle
(phase 14's higher-level admin API goes through ``AFS.users`` /
``fs.users.add`` etc., which higher layers can compose once the
byte-level mutation is proven correct).
"""

from __future__ import annotations

import pytest
from oaknut.afs import PasswordsFile, UserRecord
from oaknut.afs.passwords import ENTRY_SIZE
from oaknut.file import BootOption


def _base() -> PasswordsFile:
    return PasswordsFile.from_bytes(b"")


class TestAddUser:
    def test_add_first_user(self) -> None:
        pf = _base().with_added("Syst", system=True, quota=0x40404)
        assert pf.find("Syst").is_system
        assert pf.find("Syst").free_space == 0x40404

    def test_add_duplicate_rejected(self) -> None:
        pf = _base().with_added("alice")
        with pytest.raises(KeyError, match="already"):
            pf.with_added("alice")

    def test_add_group_user(self) -> None:
        pf = _base().with_added("dept.bob")
        user = pf.find("dept.bob")
        assert user.group == "dept"
        assert user.name == "bob"

    def test_add_two_users(self) -> None:
        pf = _base().with_added("one").with_added("two")
        names = {u.name for u in pf.active}
        assert names == {"one", "two"}


class TestRemoveUser:
    def test_remove(self) -> None:
        pf = _base().with_added("alice").with_added("bob")
        pf = pf.with_removed("alice")
        with pytest.raises(KeyError):
            pf.find("alice")
        assert pf.find("bob")

    def test_remove_missing(self) -> None:
        with pytest.raises(KeyError):
            _base().with_removed("ghost")

    def test_tombstone_reused_on_add(self) -> None:
        pf = _base().with_added("alice").with_added("bob")
        pf = pf.with_removed("alice")
        pf = pf.with_added("carol")
        # carol should occupy the slot alice vacated.
        raw = pf.to_bytes()
        assert len(raw) == 2 * ENTRY_SIZE


class TestQuotaAdmin:
    def test_set_quota(self) -> None:
        pf = _base().with_added("alice", quota=100)
        pf = pf.with_quota("alice", 500)
        assert pf.find("alice").free_space == 500

    def test_quota_out_of_range(self) -> None:
        pf = _base().with_added("alice")
        with pytest.raises(ValueError):
            pf.with_quota("alice", -1)
        with pytest.raises(ValueError):
            pf.with_quota("alice", 1 << 33)


class TestPasswordAdmin:
    def test_set_password(self) -> None:
        pf = _base().with_added("alice")
        pf = pf.with_password("alice", "secret")
        assert pf.find("alice").password == "secret"

    def test_password_too_long(self) -> None:
        pf = _base().with_added("alice")
        with pytest.raises(ValueError):
            pf.with_password("alice", "way-too-long")


class TestBootOption:
    def test_default_is_off(self) -> None:
        pf = _base().with_added("alice")
        assert pf.find("alice").boot_option == BootOption.OFF

    def test_set_boot_run(self) -> None:
        pf = _base().with_added("alice")
        pf = pf.with_boot_option("alice", BootOption.RUN)
        assert pf.find("alice").boot_option == BootOption.RUN


class TestSystem:
    def test_grant_system(self) -> None:
        pf = _base().with_added("alice")
        pf = pf.with_system("alice", True)
        assert pf.find("alice").is_system

    def test_revoke_system(self) -> None:
        pf = _base().with_added("alice", system=True)
        pf = pf.with_system("alice", False)
        assert not pf.find("alice").is_system


class TestRoundTrip:
    def test_round_trip_through_bytes(self) -> None:
        pf = (
            _base()
            .with_added("Syst", system=True, quota=0x40404)
            .with_added("alice", password="secret", quota=0x1000)
            .with_added("dept.bob")
        )
        raw = pf.to_bytes()
        pf2 = PasswordsFile.from_bytes(raw)
        assert [r.full_id for r in pf2.active] == ["Syst", "alice", "dept.bob"]
        assert pf2.find("alice").password == "secret"

    def test_record_uses_31_bytes(self) -> None:
        pf = _base().with_added("alice")
        assert len(pf.to_bytes()) == ENTRY_SIZE

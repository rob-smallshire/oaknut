"""Phase 19 — wfsinit.initialise full orchestration."""

from __future__ import annotations

import datetime

import pytest
from oaknut.adfs import ADFS, ADFS_L
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise
from oaknut.file import BootOption


class TestInitialise:
    def test_initialise_produces_afs_partition(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="TestDisc",
                date=datetime.date(2026, 4, 11),
                size=AFSSizeSpec.cylinders(20),
                users=[
                    UserSpec("Syst", system=True),
                    UserSpec("guest"),
                ],
            ),
        )
        afs = adfs.afs_partition
        assert afs is not None
        assert afs.disc_name == "TestDisc"
        assert afs.start_cylinder == 80 - 20

    def test_initialised_users_visible(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="UsersTest",
                size=AFSSizeSpec.cylinders(20),
                users=[
                    UserSpec("Syst", system=True),
                    UserSpec("alice", password="s3cret", quota=0x10000),
                    UserSpec("bob"),
                ],
            ),
        )
        afs = adfs.afs_partition
        active = {u.name for u in afs.users.active}
        assert active == {"Syst", "alice", "bob"}
        assert afs.users.find("Syst").is_system
        assert afs.users.find("alice").password == "s3cret"
        assert afs.users.find("alice").free_space == 0x10000

    def test_initialised_root_is_empty_except_passwords(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="Empty",
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("Syst", system=True)],
            ),
        )
        afs = adfs.afs_partition
        names = [p.name for p in afs.root]
        assert "Passwords" in names
        # Filter out the passwords file; there should be nothing else.
        non_passwords = [n for n in names if n != "Passwords"]
        assert non_passwords == []

    def test_write_file_after_initialise(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="WritesOK",
                size=AFSSizeSpec.cylinders(30),
                users=[UserSpec("Syst", system=True)],
            ),
        )
        afs = adfs.afs_partition
        (afs.root / "Hello").write_bytes(b"hello world")
        assert (afs.root / "Hello").read_bytes() == b"hello world"

    def test_default_quota_applied(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="Quota",
                size=AFSSizeSpec.cylinders(20),
                default_quota=0xAA00,
                users=[UserSpec("Syst", system=True), UserSpec("bob")],
            ),
        )
        afs = adfs.afs_partition
        assert afs.users.find("bob").free_space == 0xAA00
        assert afs.users.find("Syst").free_space == 0xAA00

    def test_initspec_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError):
            InitSpec(disc_name="")

    def test_initspec_rejects_duplicate_user(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            InitSpec(
                disc_name="Dup",
                users=[UserSpec("Alice"), UserSpec("alice")],
            )

    def test_boot_option_persists(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="BootTest",
                size=AFSSizeSpec.cylinders(20),
                users=[
                    UserSpec("Syst", system=True, boot=BootOption.RUN),
                ],
            ),
        )
        afs = adfs.afs_partition
        assert afs.users.find("Syst").boot_option == BootOption.RUN

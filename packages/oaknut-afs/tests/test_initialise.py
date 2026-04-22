"""Phase 19 — wfsinit.initialise full orchestration."""

from __future__ import annotations

import datetime

import pytest
from oaknut.adfs import ADFS, ADFS_L
from oaknut.afs.exceptions import (
    AFSDiscNameError,
    AFSInitSpecError,
    AFSPasswordError,
    AFSQuotaError,
    AFSUserNameError,
)
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise
from oaknut.file import BootOption

# The three built-in password entries that initialise() always creates
# (matching WFSINIT.bas lines 2140-2160): Syst, Boot, Welcome.
_BUILTIN_USERS = {"Syst", "Boot", "Welcome"}


class TestInitialise:
    def test_initialise_produces_afs_partition(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="TestDisc",
                date=datetime.date(2026, 4, 11),
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("guest")],
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
                    UserSpec("alice", password="s3cret", quota=0x10000),
                    UserSpec("bob"),
                ],
            ),
        )
        afs = adfs.afs_partition
        active = {u.name for u in afs.users.active}
        assert active == _BUILTIN_USERS | {"alice", "bob"}
        assert afs.users.find("Syst").is_system
        assert afs.users.find("alice").password == "s3cret"
        assert afs.users.find("alice").free_space == 0x10000

    def test_initialised_root_has_passwords_and_urds(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="Empty",
                size=AFSSizeSpec.cylinders(20),
                users=[],
            ),
        )
        afs = adfs.afs_partition
        names = [p.name for p in afs.root]
        # With no user-specified accounts, root should only have
        # the Passwords file — built-in accounts don't get URDs.
        assert names == ["Passwords"]

    def test_initialised_root_has_user_urds(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="WithURDs",
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("Holmes"), UserSpec("Moriarty")],
            ),
        )
        afs = adfs.afs_partition
        names = sorted(p.name for p in afs.root)
        # Each user-specified account gets a URD in root.
        assert names == ["Holmes", "Moriarty", "Passwords"]

    def test_write_file_after_initialise(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="WritesOK",
                size=AFSSizeSpec.cylinders(30),
                users=[],
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
                users=[UserSpec("bob")],
            ),
        )
        afs = adfs.afs_partition
        assert afs.users.find("bob").free_space == 0xAA00
        # Built-in accounts also receive the default quota.
        assert afs.users.find("Syst").free_space == 0xAA00

    def test_initspec_rejects_empty_name(self) -> None:
        with pytest.raises(AFSDiscNameError):
            InitSpec(disc_name="")

    def test_initspec_rejects_duplicate_user(self) -> None:
        with pytest.raises(AFSUserNameError, match="duplicate"):
            InitSpec(
                disc_name="Dup",
                users=[UserSpec("Alice"), UserSpec("alice")],
            )

    @pytest.mark.parametrize("name", ["Syst", "Boot", "Welcome", "syst", "BOOT"])
    def test_initspec_rejects_builtin_names(self, name: str) -> None:
        with pytest.raises(AFSUserNameError, match="reserved"):
            InitSpec(
                disc_name="Reserved",
                users=[UserSpec(name)],
            )

    def test_omit_builtins_suppresses_accounts(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="Omitted",
                size=AFSSizeSpec.cylinders(20),
                users=[],
                omit_builtins=frozenset({"Boot", "Welcome"}),
            ),
        )
        afs = adfs.afs_partition
        active = {u.name for u in afs.users.active}
        assert "Syst" in active
        assert "Boot" not in active
        assert "Welcome" not in active

    def test_omit_builtins_rejects_unknown_names(self) -> None:
        with pytest.raises(AFSInitSpecError, match="not a built-in"):
            InitSpec(
                disc_name="Bad",
                omit_builtins=frozenset({"Gandalf"}),
            )

    def test_boot_option_persists(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="BootTest",
                size=AFSSizeSpec.cylinders(20),
                users=[
                    UserSpec("alice", boot=BootOption.RUN),
                ],
            ),
        )
        afs = adfs.afs_partition
        assert afs.users.find("alice").boot_option == BootOption.RUN

    @pytest.mark.parametrize("initial_boot_option", [0, 1, 2, 3])
    def test_initialise_leaves_adfs_boot_option_alone(
        self, initial_boot_option: int
    ) -> None:
        adfs = ADFS.create(ADFS_L, boot_option=initial_boot_option)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="NoTouch",
                size=AFSSizeSpec.cylinders(20),
                users=[],
            ),
        )
        assert adfs.boot_option == initial_boot_option


class TestInitSpecEagerValidation:
    """Validation that must run at ``InitSpec``/``UserSpec`` construction,
    before any disc mutation.  See issue #3.
    """

    @pytest.mark.parametrize(
        "bad_name",
        [
            "Has Space",          # space in the middle
            " LeadingSpace",      # leading space
            "TrailingSpace ",     # trailing space
            "Non\x00Printable",   # NUL
            "Bell\x07Inside",     # control character
            "Café",               # non-ASCII
            "A" * 17,             # too long
        ],
    )
    def test_initspec_rejects_invalid_disc_name(self, bad_name: str) -> None:
        with pytest.raises(AFSDiscNameError):
            InitSpec(disc_name=bad_name)

    def test_userspec_rejects_empty_name(self) -> None:
        with pytest.raises(AFSUserNameError, match="name"):
            UserSpec(name="")

    def test_userspec_rejects_overlong_name(self) -> None:
        with pytest.raises(AFSUserNameError, match="21|20"):
            UserSpec(name="A" * 21)

    def test_userspec_rejects_non_ascii_name(self) -> None:
        with pytest.raises(AFSUserNameError, match="ASCII|ascii"):
            UserSpec(name="Renée")

    def test_userspec_rejects_overlong_password(self) -> None:
        with pytest.raises(AFSPasswordError, match="password"):
            UserSpec(name="alice", password="sevenCh")

    def test_userspec_rejects_non_ascii_password(self) -> None:
        with pytest.raises(AFSPasswordError, match="ASCII|ascii"):
            UserSpec(name="alice", password="pw£")

    @pytest.mark.parametrize("bad_quota", [-1, 0x1_0000_0000])
    def test_userspec_rejects_out_of_range_quota(self, bad_quota: int) -> None:
        with pytest.raises(AFSQuotaError, match="quota"):
            UserSpec(name="alice", quota=bad_quota)

    def test_initspec_rejects_out_of_range_default_quota(self) -> None:
        with pytest.raises(AFSQuotaError, match="default_quota"):
            InitSpec(disc_name="Big", default_quota=0x1_0000_0000)

    def test_invalid_spec_leaves_disc_untouched(self) -> None:
        """Constructing an invalid spec must not mutate any disc —
        the exact scenario from issue #3 reproduction.
        """
        adfs = ADFS.create(ADFS_L)
        before = bytes(adfs._disc.sector_range(0, adfs.geometry.total_sectors))
        with pytest.raises(AFSDiscNameError):
            InitSpec(disc_name="Has Space")
        after = bytes(adfs._disc.sector_range(0, adfs.geometry.total_sectors))
        assert before == after

    def test_failing_initialise_leaves_disc_untouched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a validation error somehow escapes InitSpec and fires
        inside initialise(), the disc must still be byte-identical
        to its pre-call state.  Exercises the restructured
        mutation-last ordering (defence in depth).
        """
        from oaknut.afs import info_sector as info_sector_mod

        adfs = ADFS.create(ADFS_L)
        before = bytes(adfs._disc.sector_range(0, adfs.geometry.total_sectors))

        # Force an error from InfoSector construction by patching
        # _encode_disc_name to raise unconditionally.  This simulates
        # a yet-to-be-added validation slipping past InitSpec.
        original = info_sector_mod._encode_disc_name

        def failing(name: str) -> bytes:
            raise ValueError("simulated deep-stack validation failure")

        monkeypatch.setattr(info_sector_mod, "_encode_disc_name", failing)

        with pytest.raises(ValueError, match="simulated"):
            initialise(
                adfs,
                spec=InitSpec(
                    disc_name="Valid",
                    size=AFSSizeSpec.cylinders(20),
                    users=[],
                ),
            )

        # Restore before comparing so the compare itself doesn't recurse.
        monkeypatch.setattr(info_sector_mod, "_encode_disc_name", original)
        after = bytes(adfs._disc.sector_range(0, adfs.geometry.total_sectors))
        assert before == after

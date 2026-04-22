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


class TestBuiltinOverride:
    """A ``UserSpec`` whose name matches a built-in (``Syst``, ``Boot``,
    ``Welcome``) overrides that built-in's default quota / password /
    privileges / boot option.  The built-in's system-flag cannot be
    changed and no URD is created (built-ins never have URDs).  See
    issue #4.
    """

    def test_override_syst_quota(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="OverSyst",
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("Syst", system=True, quota=4 * 1024 * 1024)],
            ),
        )
        afs = adfs.afs_partition
        assert afs.users.find("Syst").free_space == 4 * 1024 * 1024
        assert afs.users.find("Syst").is_system
        # Boot and Welcome keep the default quota.
        assert afs.users.find("Boot").free_space == 0x40404
        assert afs.users.find("Welcome").free_space == 0x40404

    def test_override_boot_quota(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="OverBoot",
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("Boot", quota=0x1000)],
            ),
        )
        afs = adfs.afs_partition
        assert afs.users.find("Boot").free_space == 0x1000
        assert not afs.users.find("Boot").is_system
        assert afs.users.find("Syst").free_space == 0x40404

    def test_override_welcome_quota(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="OverWelc",
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("Welcome", quota=0x2000)],
            ),
        )
        afs = adfs.afs_partition
        assert afs.users.find("Welcome").free_space == 0x2000

    def test_override_syst_password(self) -> None:
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="SystPass",
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("Syst", system=True, password="hunter")],
            ),
        )
        afs = adfs.afs_partition
        assert afs.users.find("Syst").password == "hunter"

    def test_override_case_insensitive(self) -> None:
        """Lowercase / mixed-case names still match the built-in."""
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="CaseOver",
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("syst", system=True, quota=0x50000)],
            ),
        )
        afs = adfs.afs_partition
        assert afs.users.find("Syst").free_space == 0x50000

    def test_override_built_in_creates_no_urd(self) -> None:
        """Overriding a built-in must not create a URD for it."""
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="NoSystURD",
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("Syst", system=True, quota=0x50000)],
            ),
        )
        afs = adfs.afs_partition
        # Root should contain only the Passwords file — no Syst URD.
        names = sorted(p.name for p in afs.root)
        assert names == ["Passwords"]

    def test_syst_override_must_be_system(self) -> None:
        """Syst is a system account; an override without ``system=True``
        is inconsistent and must be rejected.
        """
        with pytest.raises(AFSUserNameError, match="system"):
            InitSpec(
                disc_name="Bad",
                users=[UserSpec("Syst", quota=0x1000)],
            )

    @pytest.mark.parametrize("name", ["Boot", "Welcome"])
    def test_non_system_builtin_override_rejects_system_flag(
        self, name: str
    ) -> None:
        """Boot and Welcome are non-system accounts; overriding with
        ``system=True`` is inconsistent and must be rejected.
        """
        with pytest.raises(AFSUserNameError, match="system"):
            InitSpec(
                disc_name="Bad",
                users=[UserSpec(name, system=True, quota=0x1000)],
            )

    def test_omitted_builtin_becomes_regular_user(self) -> None:
        """If a built-in is explicitly omitted, its name is free for
        a regular user (with a URD).
        """
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="FreedSyst",
                size=AFSSizeSpec.cylinders(20),
                users=[UserSpec("Syst", quota=0x10000)],
                omit_builtins=frozenset({"Syst"}),
            ),
        )
        afs = adfs.afs_partition
        syst = afs.users.find("Syst")
        assert syst.free_space == 0x10000
        assert not syst.is_system
        # The freed-up name got a URD as a regular user.
        names = sorted(p.name for p in afs.root)
        assert "Syst" in names

    def test_override_ordering_preserved(self) -> None:
        """Syst must still appear before Boot in the passwords file
        even when overridden, and user-specified accounts after.
        """
        adfs = ADFS.create(ADFS_L)
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="OrderTest",
                size=AFSSizeSpec.cylinders(20),
                users=[
                    UserSpec("alice"),
                    UserSpec("Syst", system=True, quota=0x50000),
                ],
            ),
        )
        afs = adfs.afs_partition
        names_in_order = [u.name for u in afs.users.active]
        # Built-ins come first, Syst/Boot/Welcome ordering preserved,
        # then user-specified accounts.
        assert names_in_order.index("Syst") < names_in_order.index("Boot")
        assert names_in_order.index("Welcome") < names_in_order.index("alice")

    def test_duplicate_override_still_rejected(self) -> None:
        """Two overrides for the same built-in is a duplicate."""
        with pytest.raises(AFSUserNameError, match="duplicate"):
            InitSpec(
                disc_name="Dup",
                users=[
                    UserSpec("Syst", system=True, quota=0x10000),
                    UserSpec("syst", system=True, quota=0x20000),
                ],
            )

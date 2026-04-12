"""Follow-up 5 — quota enforcement on writes."""

from __future__ import annotations

import datetime

import pytest
from oaknut.adfs import ADFS, ADFS_L
from oaknut.afs import AFSQuotaExceededError
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise


def _init_disc(*, quota: int) -> ADFS:
    adfs = ADFS.create(ADFS_L)
    initialise(
        adfs,
        spec=InitSpec(
            disc_name="QuotaTest",
            date=datetime.date(2026, 4, 12),
            size=AFSSizeSpec.cylinders(30),
            default_quota=quota,
            users=[
                UserSpec("Syst", system=True),
                UserSpec("alice"),
            ],
        ),
    )
    return adfs


class TestQuotaEnforcement:
    def test_write_within_quota_succeeds(self) -> None:
        adfs = _init_disc(quota=0x10000)
        afs = adfs.afs_partition
        (afs.root / "Small").write_bytes(b"hello")
        assert (afs.root / "Small").read_bytes() == b"hello"

    def test_write_exceeding_quota_refused(self) -> None:
        adfs = _init_disc(quota=256)  # 1 sector
        afs = adfs.afs_partition
        # Default acting user is "Syst". 2 data sectors + 1 map block
        # = 3 sectors × 256 = 768 bytes cost, exceeds the 256 quota.
        with pytest.raises(AFSQuotaExceededError, match="Syst"):
            (afs.root / "Big").write_bytes(
                b"x" * 300,  # > 256, needs 2 data sectors
            )

    def test_delete_credits_quota(self) -> None:
        adfs = _init_disc(quota=0x10000)
        afs = adfs.afs_partition
        old_free = afs.users.find("Syst").free_space
        (afs.root / "File").write_bytes(b"hello")
        mid_free = afs.users.find("Syst").free_space
        assert mid_free < old_free
        (afs.root / "File").unlink()
        new_free = afs.users.find("Syst").free_space
        assert new_free == old_free

    def test_enforce_quota_false_bypasses(self) -> None:
        from oaknut.afs.afs import AFS

        adfs = _init_disc(quota=1)  # tiny
        sec1, sec2 = adfs._fsm.afs_info_pointers
        afs = AFS(adfs._disc, sec1, sec2, enforce_quota=False)
        # Should NOT raise even though quota is 1 byte.
        (afs.root / "Big").write_bytes(b"x" * 500)
        afs.flush()
        assert (afs.root / "Big").read_bytes() == b"x" * 500

"""Tests for AFS info-sector pointer install / read on the old free-space map.

These are the ADFS-side primitives used by
``ADFS.afs_partition`` and by ``wfsinit.partition.apply`` (phase 15).
"""

from __future__ import annotations

import pytest
from oaknut.adfs import ADFS, ADFS_L


class TestAfsInfoPointers:
    def test_blank_disc_reports_zero_pointers(self) -> None:
        adfs = ADFS.create(ADFS_L)
        assert adfs._fsm.afs_info_pointers == (0, 0)

    def test_install_round_trips(self) -> None:
        adfs = ADFS.create(ADFS_L)
        adfs._fsm.install_afs_pointers(0x8D1, 0x8E1)
        assert adfs._fsm.afs_info_pointers == (0x8D1, 0x8E1)

    def test_install_recomputes_checksums(self) -> None:
        adfs = ADFS.create(ADFS_L)
        adfs._fsm.install_afs_pointers(0x8D1, 0x8E1)
        # validate() returns [] on a well-formed map (checksums OK).
        assert adfs._fsm.validate() == []

    def test_afs_partition_none_when_not_installed(self) -> None:
        adfs = ADFS.create(ADFS_L)
        assert adfs.afs_partition is None

    def test_install_rejects_out_of_range(self) -> None:
        adfs = ADFS.create(ADFS_L)
        with pytest.raises(ValueError):
            adfs._fsm.install_afs_pointers(-1, 0)
        with pytest.raises(ValueError):
            adfs._fsm.install_afs_pointers(0, 1 << 33)

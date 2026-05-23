"""Capacity strings on ADFS.create_file and UserSpec.quota (#30)."""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs import ADFS


class TestADFSCreateFileCapacityString:
    def test_capacity_str_megabytes(self, tmp_path: Path) -> None:
        filepath = tmp_path / "scsi0.dat"
        with ADFS.create_file(filepath, capacity="10MB") as adfs:
            # 10MB == 10_000_000 bytes — the underlying file should be
            # at least that big (geometry rounds up to whole cylinders).
            assert adfs.geometry.total_sectors * 256 >= 10_000_000

    def test_capacity_int_bytes(self, tmp_path: Path) -> None:
        filepath = tmp_path / "scsi0.dat"
        with ADFS.create_file(filepath, capacity=5_000_000) as adfs:
            assert adfs.geometry.total_sectors * 256 >= 5_000_000

    def test_capacity_str_mib(self, tmp_path: Path) -> None:
        filepath = tmp_path / "scsi0.dat"
        with ADFS.create_file(filepath, capacity="5MiB") as adfs:
            assert adfs.geometry.total_sectors * 256 >= 5 * 1024 * 1024


class TestUserSpecQuotaString:
    def test_quota_str_megabytes(self) -> None:
        from oaknut.afs import UserSpec

        spec = UserSpec("alice", quota="2MB")
        assert spec.quota == 2_000_000

    def test_quota_int_bytes_unchanged(self) -> None:
        from oaknut.afs import UserSpec

        spec = UserSpec("alice", quota=1_048_576)
        assert spec.quota == 1_048_576

    def test_quota_none_unchanged(self) -> None:
        from oaknut.afs import UserSpec

        spec = UserSpec("alice")
        assert spec.quota is None

    def test_quota_str_kib(self) -> None:
        from oaknut.afs import UserSpec

        spec = UserSpec("alice", quota="512KiB")
        assert spec.quota == 512 * 1024

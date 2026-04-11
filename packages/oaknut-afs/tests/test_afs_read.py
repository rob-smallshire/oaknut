"""End-to-end read-path tests for the ``AFS`` handle.

These tests exercise the full stack — :class:`AFS`, :class:`AFSPath`,
:class:`AfsDirectory`, :class:`MapSector`, :class:`ExtentStream`,
:class:`PasswordsFile`, the ADFS integration — against a synthetic
in-memory disc built by :mod:`helpers.afs_image`.
"""

from __future__ import annotations

import pytest
from helpers.afs_image import (
    DEFAULT_START_CYLINDER,
    SyntheticFile,
    SyntheticUser,
    build_synthetic_adfs_with_afs,
)
from oaknut.adfs import ADFS_L
from oaknut.afs import AFS, AFSPathError, PasswordsFile
from oaknut.afs.path import AFSPath


class TestAFSPartitionDetection:
    def test_blank_disc_has_no_afs(self) -> None:
        from oaknut.adfs import ADFS

        adfs = ADFS.create(ADFS_L)
        assert adfs.afs_partition is None

    def test_patched_disc_has_afs(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        assert isinstance(afs, AFS)

    def test_disc_name_from_info_sector(self) -> None:
        adfs = build_synthetic_adfs_with_afs(disc_name="HelloThere")
        assert adfs.afs_partition.disc_name == "HelloThere"

    def test_start_cylinder(self) -> None:
        adfs = build_synthetic_adfs_with_afs(start_cylinder=150)
        assert adfs.afs_partition.start_cylinder == 150

    def test_geometry_matches_info_sector(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        geom = adfs.afs_partition.geometry
        assert geom.total_sectors == ADFS_L.total_sectors
        assert geom.sectors_per_cylinder == 16


class TestRootDirectoryIteration:
    def test_root_lists_files(self) -> None:
        adfs = build_synthetic_adfs_with_afs(
            root_files=[
                SyntheticFile(name="Alpha", contents=b"alpha body"),
                SyntheticFile(name="Beta", contents=b"beta body data"),
            ]
        )
        afs = adfs.afs_partition
        names = sorted(p.name for p in afs.root)
        assert "Alpha" in names
        assert "Beta" in names
        assert "Passwords" in names

    def test_root_path_is_bound(self) -> None:
        afs = build_synthetic_adfs_with_afs().afs_partition
        assert afs.root.afs is afs

    def test_unbound_path_refuses_io(self) -> None:
        p = AFSPath.root() / "Alpha"
        with pytest.raises(AFSPathError, match="not bound"):
            p.read_bytes()


class TestReadBytes:
    def test_round_trip_small_file(self) -> None:
        payload = b"Hello, AFS!\n"
        adfs = build_synthetic_adfs_with_afs(
            root_files=[SyntheticFile(name="Hello", contents=payload)]
        )
        afs = adfs.afs_partition
        assert (afs.root / "Hello").read_bytes() == payload

    def test_round_trip_multi_sector_file(self) -> None:
        payload = bytes((i * 7 + 13) & 0xFF for i in range(1200))  # 5 sectors
        adfs = build_synthetic_adfs_with_afs(
            root_files=[SyntheticFile(name="Big", contents=payload)]
        )
        afs = adfs.afs_partition
        assert (afs.root / "Big").read_bytes() == payload

    def test_read_bytes_on_directory_rejected(self) -> None:
        afs = build_synthetic_adfs_with_afs().afs_partition
        with pytest.raises(AFSPathError, match="cannot read_bytes|is a directory"):
            afs.root.read_bytes()


class TestStat:
    def test_stat_returns_directory_entry(self) -> None:
        adfs = build_synthetic_adfs_with_afs(
            root_files=[SyntheticFile(name="Hello", contents=b"hi")]
        )
        entry = (adfs.afs_partition.root / "Hello").stat()
        assert entry.name == "Hello"
        assert entry.load_address == 0x00008000


class TestIsDirIsFile:
    def test_root_is_dir(self) -> None:
        afs = build_synthetic_adfs_with_afs().afs_partition
        assert afs.root.is_dir()
        assert not afs.root.is_file()

    def test_file_is_file(self) -> None:
        afs = build_synthetic_adfs_with_afs(
            root_files=[SyntheticFile(name="Hello", contents=b"x")]
        ).afs_partition
        assert (afs.root / "Hello").is_file()
        assert not (afs.root / "Hello").is_dir()

    def test_exists_true(self) -> None:
        afs = build_synthetic_adfs_with_afs(
            root_files=[SyntheticFile(name="Hello", contents=b"x")]
        ).afs_partition
        assert (afs.root / "Hello").exists()

    def test_exists_false(self) -> None:
        afs = build_synthetic_adfs_with_afs().afs_partition
        assert not (afs.root / "Missing").exists()


class TestPasswordsFile:
    def test_parses_users(self) -> None:
        afs = build_synthetic_adfs_with_afs(
            users=[
                SyntheticUser("Syst", system=True),
                SyntheticUser("alice", password="s3cret", free_space=0x1000),
                SyntheticUser("bob"),
            ],
        ).afs_partition
        users = afs.users
        assert isinstance(users, PasswordsFile)
        assert {u.name for u in users.active} == {"Syst", "alice", "bob"}

    def test_system_user_flag(self) -> None:
        afs = build_synthetic_adfs_with_afs(
            users=[SyntheticUser("Syst", system=True), SyntheticUser("guest")]
        ).afs_partition
        assert afs.users.find("Syst").is_system
        assert not afs.users.find("guest").is_system

    def test_find_by_name_missing(self) -> None:
        afs = build_synthetic_adfs_with_afs(
            users=[SyntheticUser("Syst", system=True)]
        ).afs_partition
        with pytest.raises(KeyError):
            afs.users.find("nobody")

    def test_free_space_from_quota(self) -> None:
        afs = build_synthetic_adfs_with_afs(
            users=[SyntheticUser("alice", free_space=0xDEAD00)],
        ).afs_partition
        assert afs.users.find("alice").free_space == 0xDEAD00


class TestFlush:
    def test_flush_is_noop_in_read_only(self) -> None:
        afs = build_synthetic_adfs_with_afs().afs_partition
        afs.flush()

    def test_context_manager(self) -> None:
        afs = build_synthetic_adfs_with_afs().afs_partition
        with afs as same:
            assert same is afs


class TestStartCylinderPassThrough:
    def test_start_cylinder_default(self) -> None:
        afs = build_synthetic_adfs_with_afs().afs_partition
        assert afs.start_cylinder == DEFAULT_START_CYLINDER

"""Phase 11-13 — file / directory create, write, and delete.

End-to-end tests for ``AFSPath.write_bytes``, ``AFSPath.mkdir``,
``AFSPath.unlink``, and ``AFSPath.rmdir`` against a synthetic AFS
image. Each operation is driven through the public path surface
and verified by re-reading the affected objects.
"""

from __future__ import annotations

import datetime

import pytest
from helpers.afs_image import build_synthetic_adfs_with_afs
from oaknut.afs import (
    AFSAccess,
    AfsDate,
    AFSDirectoryNotEmptyError,
    AFSFileLockedError,
)


class TestWriteBytesCreate:
    def test_create_small_file(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        path = afs.root / "NewFile"
        path.write_bytes(b"hello")
        assert path.exists()
        assert path.read_bytes() == b"hello"

    def test_create_sector_aligned_file(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        payload = bytes(range(256)) * 3  # exactly 3 sectors
        (afs.root / "Aligned").write_bytes(payload)
        assert (afs.root / "Aligned").read_bytes() == payload

    def test_create_multi_sector_with_partial_tail(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        payload = b"x" * 500  # 2 sectors, 244 bytes used in last
        (afs.root / "Partial").write_bytes(payload)
        assert (afs.root / "Partial").read_bytes() == payload

    def test_create_empty_file(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Empty").write_bytes(b"")
        assert (afs.root / "Empty").read_bytes() == b""

    def test_write_preserves_metadata(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Meta").write_bytes(
            b"data",
            load_address=0xDEADBEEF,
            exec_address=0xCAFEBABE,
            access=AFSAccess.from_string("LR/R"),
            date=AfsDate(datetime.date(2025, 1, 2)),
        )
        entry = (afs.root / "Meta").stat()
        assert entry.load_address == 0xDEADBEEF
        assert entry.exec_address == 0xCAFEBABE

    def test_write_many_files(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        for i in range(30):
            (afs.root / f"F{i:03d}").write_bytes(f"body-{i}".encode())
        for i in range(30):
            assert (afs.root / f"F{i:03d}").read_bytes() == f"body-{i}".encode()

    def test_write_replaces_existing(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Same").write_bytes(b"first")
        (afs.root / "Same").write_bytes(b"second")
        assert (afs.root / "Same").read_bytes() == b"second"


class TestMkdir:
    def test_create_directory(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Docs").mkdir()
        assert (afs.root / "Docs").exists()
        assert (afs.root / "Docs").is_dir()

    def test_create_file_inside_subdir(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Dir").mkdir()
        (afs.root / "Dir" / "Inner").write_bytes(b"nested")
        assert (afs.root / "Dir" / "Inner").read_bytes() == b"nested"

    def test_nested_directories(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "A").mkdir()
        (afs.root / "A" / "B").mkdir()
        (afs.root / "A" / "B" / "file").write_bytes(b"deep")
        assert (afs.root / "A" / "B" / "file").read_bytes() == b"deep"


class TestUnlink:
    def test_delete_file(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Doomed").write_bytes(b"bye")
        assert (afs.root / "Doomed").exists()
        (afs.root / "Doomed").unlink()
        assert not (afs.root / "Doomed").exists()

    def test_delete_frees_space(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        free_before = afs.free_sectors
        (afs.root / "Big").write_bytes(b"x" * 1000)  # 4 sectors + map block
        free_after_create = afs.free_sectors
        assert free_after_create < free_before
        (afs.root / "Big").unlink()
        free_after_delete = afs.free_sectors
        assert free_after_delete == free_before

    def test_delete_empty_directory(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Empty").mkdir()
        (afs.root / "Empty").rmdir()
        assert not (afs.root / "Empty").exists()

    def test_refuse_nonempty_directory(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Dir").mkdir()
        (afs.root / "Dir" / "child").write_bytes(b"")
        with pytest.raises(AFSDirectoryNotEmptyError):
            (afs.root / "Dir").unlink()

    def test_refuse_locked_file(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Locked").write_bytes(
            b"data", access=AFSAccess.from_string("LR/R")
        )
        # LR/R access has the L bit set per AFSAccess.from_string.
        with pytest.raises(AFSFileLockedError):
            (afs.root / "Locked").unlink()

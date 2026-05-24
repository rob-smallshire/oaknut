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
    AFSDirectoryEntryExistsError,
    AFSDirectoryNotEmptyError,
    AFSFileLockedError,
    AFSPathError,
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

    def test_mkdir_existing_raises(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Dir").mkdir()
        with pytest.raises(AFSDirectoryEntryExistsError):
            (afs.root / "Dir").mkdir()

    def test_mkdir_parent_not_found_raises(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(AFSPathError):
            (afs.root / "Missing" / "Sub").mkdir()


class TestMkdirExistOk:
    """``exist_ok=True`` mirrors ``pathlib.Path.mkdir``: swallows the
    "already exists" error only when the existing entry is itself a
    directory, never when it is a file.
    """

    def test_exist_ok_true_silent_when_directory_already_exists(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Dir").mkdir()
        (afs.root / "Dir").mkdir(exist_ok=True)  # no exception

    def test_exist_ok_true_still_raises_when_file_already_exists(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Name").write_bytes(b"file data")
        with pytest.raises(AFSPathError, match="already exists"):
            (afs.root / "Name").mkdir(exist_ok=True)

    def test_exist_ok_false_still_raises_when_directory_exists(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Dir").mkdir()
        with pytest.raises(AFSDirectoryEntryExistsError):
            (afs.root / "Dir").mkdir(exist_ok=False)

    def test_exist_ok_true_does_not_clobber_existing_directory_contents(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Dir").mkdir()
        (afs.root / "Dir" / "Inner").write_bytes(b"keep me")
        (afs.root / "Dir").mkdir(exist_ok=True)
        assert (afs.root / "Dir" / "Inner").read_bytes() == b"keep me"


class TestMkdirParents:
    """``parents=True`` mirrors ``pathlib.Path.mkdir``: creates any
    missing intermediate directories.
    """

    def test_parents_false_raises_when_intermediate_missing(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(AFSPathError):
            (afs.root / "Missing" / "Sub").mkdir()

    def test_parents_true_creates_intermediates(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "A" / "B" / "C").mkdir(parents=True)
        assert (afs.root / "A").is_dir()
        assert (afs.root / "A" / "B").is_dir()
        assert (afs.root / "A" / "B" / "C").is_dir()

    def test_parents_true_succeeds_when_intermediates_exist(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "A").mkdir()
        (afs.root / "A" / "B" / "C").mkdir(parents=True)
        assert (afs.root / "A" / "B" / "C").is_dir()

    def test_parents_true_still_raises_on_existing_target_without_exist_ok(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "A" / "B").mkdir(parents=True)
        with pytest.raises(AFSDirectoryEntryExistsError):
            (afs.root / "A" / "B").mkdir(parents=True)

    def test_parents_true_and_exist_ok_true_fully_idempotent(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "A" / "B" / "C").mkdir(parents=True, exist_ok=True)
        (afs.root / "A" / "B" / "C").mkdir(parents=True, exist_ok=True)
        assert (afs.root / "A" / "B" / "C").is_dir()


class TestTouch:
    """``touch()`` creates an empty file at the path.

    Mirrors :meth:`pathlib.Path.touch`.
    """

    def test_touch_creates_empty_file(self) -> None:
        from oaknut.file import Access

        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Fresh").touch()
        assert (afs.root / "Fresh").exists()
        assert (afs.root / "Fresh").read_bytes() == b""
        assert not (afs.root / "Fresh").stat().access & Access.L

    def test_touch_applies_access_on_create(self) -> None:
        from oaknut.file import Access

        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Locked").touch(access=AFSAccess.from_string("LR/"))
        assert (afs.root / "Locked").stat().access & Access.L

    def test_touch_default_exist_ok_is_true(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Hello").write_bytes(b"keep")
        (afs.root / "Hello").touch()
        assert (afs.root / "Hello").read_bytes() == b"keep"

    def test_touch_exist_ok_false_raises_when_file_exists(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Hello").write_bytes(b"x")
        with pytest.raises(AFSDirectoryEntryExistsError):
            (afs.root / "Hello").touch(exist_ok=False)

    def test_touch_raises_when_path_is_existing_directory(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        (afs.root / "Dir").mkdir()
        with pytest.raises(AFSPathError):
            (afs.root / "Dir").touch()

    def test_touch_root_raises(self) -> None:
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(AFSPathError):
            afs.root.touch()


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
        (afs.root / "Locked").write_bytes(b"data", access=AFSAccess.from_string("LR/R"))
        # LR/R access has the L bit set per AFSAccess.from_string.
        with pytest.raises(AFSFileLockedError):
            (afs.root / "Locked").unlink()

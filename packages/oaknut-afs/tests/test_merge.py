"""Phase 16 — AFS → AFS subtree copy."""

from __future__ import annotations

import pytest
from helpers.afs_image import build_synthetic_adfs_with_afs
from oaknut.afs import AFSMergeConflictError, merge


def _make_source_tree(afs) -> None:
    """Populate the source AFS root with a small tree."""
    (afs.root / "Docs").mkdir()
    (afs.root / "Docs" / "README").write_bytes(b"readme body")
    (afs.root / "Docs" / "NOTES").write_bytes(b"notes body")
    (afs.root / "Bin").mkdir()
    (afs.root / "Bin" / "tool").write_bytes(b"tool bytes")


class TestMergeBasics:
    def test_merge_subtree_into_target_subdirectory(self) -> None:
        src_adfs = build_synthetic_adfs_with_afs(disc_name="Src")
        tgt_adfs = build_synthetic_adfs_with_afs(disc_name="Tgt")
        src = src_adfs.afs_partition
        tgt = tgt_adfs.afs_partition
        _make_source_tree(src)

        # Copy just source's Docs subtree into the target's Library.
        merge(
            tgt,
            src,
            source_path=src.root / "Docs",
            target_path=tgt.root / "Library",
        )
        assert (tgt.root / "Library" / "README").read_bytes() == b"readme body"
        assert (tgt.root / "Library" / "NOTES").read_bytes() == b"notes body"

    def test_merge_into_subdirectory(self) -> None:
        src_adfs = build_synthetic_adfs_with_afs(disc_name="Src")
        tgt_adfs = build_synthetic_adfs_with_afs(disc_name="Tgt")
        src = src_adfs.afs_partition
        tgt = tgt_adfs.afs_partition
        _make_source_tree(src)

        merge(
            tgt,
            src,
            source_path=src.root / "Docs",
            target_path=tgt.root / "Library",
        )

        assert (tgt.root / "Library" / "README").read_bytes() == b"readme body"

    def test_merge_preserves_load_exec(self) -> None:
        src_adfs = build_synthetic_adfs_with_afs()
        tgt_adfs = build_synthetic_adfs_with_afs()
        src = src_adfs.afs_partition
        tgt = tgt_adfs.afs_partition
        (src.root / "Sub").mkdir()
        (src.root / "Sub" / "File").write_bytes(
            b"hello",
            load_address=0x11110000,
            exec_address=0x22220000,
        )
        merge(
            tgt,
            src,
            source_path=src.root / "Sub",
            target_path=tgt.root / "Landing",
        )
        entry = (tgt.root / "Landing" / "File").stat()
        assert entry.load_address == 0x11110000
        assert entry.exec_address == 0x22220000


def _setup_conflict(policy: str) -> tuple:
    """Build a src with Sub/X, Sub/Y and a tgt with Sub/X to force a conflict."""
    src_adfs = build_synthetic_adfs_with_afs()
    tgt_adfs = build_synthetic_adfs_with_afs()
    src = src_adfs.afs_partition
    tgt = tgt_adfs.afs_partition
    (src.root / "Sub").mkdir()
    (src.root / "Sub" / "X").write_bytes(b"src-x")
    (src.root / "Sub" / "Y").write_bytes(b"src-y")
    (tgt.root / "Land").mkdir()
    (tgt.root / "Land" / "X").write_bytes(b"tgt-x")
    return src, tgt


class TestConflictPolicies:
    def test_conflict_error(self) -> None:
        src, tgt = _setup_conflict("error")
        with pytest.raises(AFSMergeConflictError):
            merge(
                tgt,
                src,
                source_path=src.root / "Sub",
                target_path=tgt.root / "Land",
            )
        assert (tgt.root / "Land" / "X").read_bytes() == b"tgt-x"

    def test_conflict_skip(self) -> None:
        src, tgt = _setup_conflict("skip")
        merge(
            tgt,
            src,
            source_path=src.root / "Sub",
            target_path=tgt.root / "Land",
            conflict="skip",
        )
        assert (tgt.root / "Land" / "X").read_bytes() == b"tgt-x"
        assert (tgt.root / "Land" / "Y").read_bytes() == b"src-y"

    def test_conflict_overwrite(self) -> None:
        src, tgt = _setup_conflict("overwrite")
        merge(
            tgt,
            src,
            source_path=src.root / "Sub",
            target_path=tgt.root / "Land",
            conflict="overwrite",
        )
        assert (tgt.root / "Land" / "X").read_bytes() == b"src-x"
        assert (tgt.root / "Land" / "Y").read_bytes() == b"src-y"

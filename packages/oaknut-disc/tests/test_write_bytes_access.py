"""Cross-filesystem write_bytes(access=) conformance (#25).

Asserts that every path class accepts the same five forms on the
``access`` keyword — ``None``, ``True``, ``False``,
:class:`oaknut.file.Access`, and the filesystem's native access type
(``AFSAccess`` on AFS, an int on DFS/ADFS treated as Access bits).
The resulting on-disc state is checked via the unified
:class:`oaknut.file.Stat` protocol so the test is itself filesystem-agnostic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs import ADFS
from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS
from oaknut.file import Access


def _open_dfs(filepath: Path):
    return DFS.from_file(filepath, ACORN_DFS_80T_SINGLE_SIDED, mode="r+b")


class TestUnifiedAccessAcceptance:
    """Each path class must accept the documented forms of ``access``."""

    def test_dfs_accepts_bool_true(self, dfs_image_filepath: Path) -> None:
        with _open_dfs(dfs_image_filepath) as dfs:
            (dfs.root / "$.LOCK").write_bytes(b"x", access=True)
            assert (dfs.root / "$.LOCK").stat().access & Access.L

    def test_dfs_accepts_bool_false(self, dfs_image_filepath: Path) -> None:
        with _open_dfs(dfs_image_filepath) as dfs:
            (dfs.root / "$.OPEN").write_bytes(b"x", access=False)
            assert not ((dfs.root / "$.OPEN").stat().access & Access.L)

    def test_dfs_accepts_none(self, dfs_image_filepath: Path) -> None:
        with _open_dfs(dfs_image_filepath) as dfs:
            (dfs.root / "$.NONE").write_bytes(b"x", access=None)
            assert not ((dfs.root / "$.NONE").stat().access & Access.L)

    def test_dfs_accepts_canonical_Access(self, dfs_image_filepath: Path) -> None:
        with _open_dfs(dfs_image_filepath) as dfs:
            (dfs.root / "$.ACC").write_bytes(b"x", access=Access.L | Access.R | Access.W)
            assert (dfs.root / "$.ACC").stat().access & Access.L

    def test_adfs_accepts_bool_true(self, adfs_image_filepath: Path) -> None:
        with ADFS.from_file(adfs_image_filepath, mode="r+b") as adfs:
            (adfs.root / "Locked").write_bytes(b"x", access=True)
            assert (adfs.root / "Locked").stat().access & Access.L

    def test_adfs_accepts_canonical_Access(self, adfs_image_filepath: Path) -> None:
        with ADFS.from_file(adfs_image_filepath, mode="r+b") as adfs:
            (adfs.root / "Acc").write_bytes(b"x", access=Access.L | Access.R)
            assert (adfs.root / "Acc").stat().access & Access.L

    def test_afs_accepts_bool_true(self, afs_image_filepath: Path) -> None:
        with ADFS.from_file(afs_image_filepath, mode="r+b") as adfs:
            afs = adfs.afs_partition
            (afs.root / "Locked").write_bytes(b"x", access=True)
            from oaknut.afs import AFSAccess

            assert (afs.root / "Locked").stat().afs_access & AFSAccess.LOCKED

    def test_afs_accepts_canonical_Access(self, afs_image_filepath: Path) -> None:
        with ADFS.from_file(afs_image_filepath, mode="r+b") as adfs:
            afs = adfs.afs_partition
            (afs.root / "Acc").write_bytes(b"x", access=Access.L | Access.PR)
            from oaknut.afs import AFSAccess

            on_disc = (afs.root / "Acc").stat().afs_access
            assert on_disc & AFSAccess.LOCKED
            assert on_disc & AFSAccess.PUBLIC_READ

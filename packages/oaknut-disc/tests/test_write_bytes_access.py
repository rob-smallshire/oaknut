"""Cross-filesystem write_bytes(access=) conformance.

Every path class accepts the same access forms: None (filesystem
default), an Access flag combination, and on AFS also the native
AFSAccess or a raw int byte. The canonical patterns are
access=Access.LWR (locked owner R+W) and access=Access.WR (the
unlocked default).

On-disc state is checked via the unified oaknut.file.Stat protocol
so the test is itself filesystem-agnostic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs import ADFS
from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS
from oaknut.file import Access


def _open_dfs(filepath: Path):
    return DFS.from_file(filepath, ACORN_DFS_80T_SINGLE_SIDED)


class TestUnifiedAccessAcceptance:
    """Each path class must accept the documented forms of ``access``."""

    def test_dfs_accepts_lwr_constant_for_locked(self, dfs_image_filepath: Path) -> None:
        with _open_dfs(dfs_image_filepath) as dfs:
            (dfs.root / "$.LOCK").write_bytes(b"x", access=Access.LWR)
            assert (dfs.root / "$.LOCK").stat().access & Access.L

    def test_dfs_accepts_wr_constant_for_unlocked(self, dfs_image_filepath: Path) -> None:
        with _open_dfs(dfs_image_filepath) as dfs:
            (dfs.root / "$.OPEN").write_bytes(b"x", access=Access.WR)
            assert not ((dfs.root / "$.OPEN").stat().access & Access.L)

    def test_dfs_accepts_none(self, dfs_image_filepath: Path) -> None:
        with _open_dfs(dfs_image_filepath) as dfs:
            (dfs.root / "$.NONE").write_bytes(b"x", access=None)
            assert not ((dfs.root / "$.NONE").stat().access & Access.L)

    def test_dfs_accepts_explicit_flag_combination(self, dfs_image_filepath: Path) -> None:
        with _open_dfs(dfs_image_filepath) as dfs:
            (dfs.root / "$.ACC").write_bytes(
                b"x", access=Access.L | Access.R | Access.W
            )
            assert (dfs.root / "$.ACC").stat().access & Access.L

    def test_adfs_accepts_lwr_constant(self, adfs_image_filepath: Path) -> None:
        with ADFS.from_file(adfs_image_filepath) as adfs:
            (adfs.root / "Locked").write_bytes(b"x", access=Access.LWR)
            assert (adfs.root / "Locked").stat().access & Access.L

    def test_adfs_accepts_explicit_flag_combination(
        self, adfs_image_filepath: Path
    ) -> None:
        with ADFS.from_file(adfs_image_filepath) as adfs:
            (adfs.root / "Acc").write_bytes(b"x", access=Access.L | Access.R)
            assert (adfs.root / "Acc").stat().access & Access.L

    def test_afs_accepts_lwr_constant(self, afs_image_filepath: Path) -> None:
        with ADFS.from_file(afs_image_filepath) as adfs:
            afs = adfs.afs_partition
            (afs.root / "Locked").write_bytes(b"x", access=Access.LWR)
            from oaknut.afs import AFSAccess

            assert (afs.root / "Locked").stat().afs_access & AFSAccess.LOCKED

    def test_afs_accepts_explicit_flag_combination(
        self, afs_image_filepath: Path
    ) -> None:
        with ADFS.from_file(afs_image_filepath) as adfs:
            afs = adfs.afs_partition
            (afs.root / "Acc").write_bytes(b"x", access=Access.L | Access.PR)
            from oaknut.afs import AFSAccess

            on_disc = (afs.root / "Acc").stat().afs_access
            assert on_disc & AFSAccess.LOCKED
            assert on_disc & AFSAccess.PUBLIC_READ

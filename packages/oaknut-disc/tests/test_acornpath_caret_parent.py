"""``^`` is the Acorn shell's parent-directory token.

Each ``^`` in a slash-joined path component walks one level up the
directory tree, mirroring Acorn shell syntax. Consecutive carets
need no dot between them — ``^^`` and ``^.^`` are both "two levels
up". Hats may be combined freely with normal name components in
either order.

Tested against all three concrete path classes via the AcornPath
base contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs import ADFS, ADFS_S
from oaknut.afs import AFS
from oaknut.dfs import DFS


def _dfs_starting_point(tmp_path: Path):
    """A populated DFS disc with $.HELLO and A.GAME — yields path to $.HELLO."""
    filepath = tmp_path / "demo.ssd"
    with DFS.create_file(filepath, title="X") as dfs:
        (dfs.root / "$" / "HELLO").write_bytes(b"hello")
        (dfs.root / "A" / "GAME").write_bytes(b"game")
    with DFS.from_file(filepath) as dfs:
        yield dfs.root / "$" / "HELLO"


def _adfs_starting_point(tmp_path: Path):
    """A populated ADFS disc with $.Games.Elite and $.Docs.ReadMe."""
    adfs = ADFS.create(ADFS_S)
    (adfs.root / "Games").mkdir()
    (adfs.root / "Games" / "Elite").write_bytes(b"elite")
    (adfs.root / "Docs").mkdir()
    (adfs.root / "Docs" / "ReadMe").write_bytes(b"docs")
    yield adfs.root / "Games" / "Elite"


def _afs_starting_point(tmp_path: Path):
    filepath = tmp_path / "server.dat"
    with AFS.create_file(filepath, capacity="5MB", disc_name="X"):
        pass
    with AFS.from_file(filepath) as afs:
        (afs.root / "Games").mkdir()
        (afs.root / "Games" / "Elite").write_bytes(b"elite")
        (afs.root / "Docs").mkdir()
        (afs.root / "Docs" / "ReadMe").write_bytes(b"docs")
        yield afs.root / "Games" / "Elite"


@pytest.fixture(
    params=[_dfs_starting_point, _adfs_starting_point, _afs_starting_point],
    ids=["dfs", "adfs", "afs"],
)
def deep_path(request, tmp_path):
    """A file two levels below the nameless root, on each filesystem."""
    yield from request.param(tmp_path)


class TestCaretWalksUp:
    def test_single_caret_equals_parent(self, deep_path) -> None:
        assert (deep_path / "^").path == deep_path.parent.path

    def test_two_carets_with_dot(self, deep_path) -> None:
        assert (deep_path / "^.^").path == deep_path.parent.parent.path

    def test_two_carets_without_dot(self, deep_path) -> None:
        """Acorn syntax: dots between consecutive hats are optional."""
        assert (deep_path / "^^").path == deep_path.parent.parent.path

    def test_three_carets_without_dot(self, deep_path) -> None:
        assert (deep_path / "^^^").path == deep_path.parent.parent.parent.path

    def test_caret_chain_clamps_at_root(self, deep_path) -> None:
        """Walking up past the root stops at the root (root.parent is root)."""
        deep_root = deep_path.parent.parent.parent
        # `deep_path` is 2 levels below root; ^^^^^ would overshoot but
        # clamps because root.parent == root.
        assert (deep_path / "^^^^^").path == deep_root.path


class TestCaretMixedWithNames:
    def test_up_then_into_sibling_directory(self, deep_path) -> None:
        # From $.Games.Elite, ^.^.Docs.ReadMe = $.Docs.ReadMe (on ADFS/AFS)
        # or A.GAME via the same dance on DFS.
        sibling = deep_path.parent.parent / _sibling_path_for(deep_path)
        joined = deep_path / f"^.^.{_sibling_path_for(deep_path)}"
        assert joined.path == sibling.path

    def test_consecutive_carets_then_name(self, deep_path) -> None:
        sibling = deep_path.parent.parent / _sibling_path_for(deep_path)
        joined = deep_path / f"^^.{_sibling_path_for(deep_path)}"
        assert joined.path == sibling.path


def _sibling_path_for(deep_path) -> str:
    """Return the path string that names the sibling test file on each FS.

    Built by the fixtures above:
        DFS:  A.GAME      (a sibling directory's file)
        ADFS: Docs.ReadMe (a sibling subdirectory's file)
        AFS:  Docs.ReadMe (same)
    """
    if deep_path.__class__.__name__ == "DFSPath":
        return "A.GAME"
    return "Docs.ReadMe"

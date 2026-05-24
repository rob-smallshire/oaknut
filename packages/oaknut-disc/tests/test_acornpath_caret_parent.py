"""``^`` is the Acorn shell's parent-directory token.

Carets are stored as literal path components by slash-join — the
same way :class:`pathlib.PurePath` stores ``..`` — and
:meth:`AcornPath.resolve` collapses them. Consecutive carets need
no dot between them: ``^^`` and ``^.^`` are stored as one
component and two components respectively but resolve identically.

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


class TestCaretsAreStoredLiterally:
    def test_single_caret_is_stored(self, deep_path) -> None:
        joined = deep_path / "^"
        assert joined.parts[-1] == "^"
        # The literal path string ends with the caret.
        assert joined.path.endswith("^")

    def test_consecutive_carets_keep_one_component(self, deep_path) -> None:
        joined = deep_path / "^^"
        assert joined.parts[-1] == "^^"

    def test_dotted_carets_split_into_components(self, deep_path) -> None:
        joined = deep_path / "^.^"
        assert joined.parts[-2:] == ("^", "^")


class TestResolveCollapsesCarets:
    def test_single_caret_resolves_to_parent(self, deep_path) -> None:
        assert (deep_path / "^").resolve().path == deep_path.parent.path

    def test_two_carets_with_dot_resolves_to_grandparent(self, deep_path) -> None:
        assert (deep_path / "^.^").resolve().path == deep_path.parent.parent.path

    def test_two_carets_without_dot_resolves_to_grandparent(self, deep_path) -> None:
        """Acorn syntax: dots between consecutive hats are optional."""
        assert (deep_path / "^^").resolve().path == deep_path.parent.parent.path

    def test_three_carets_resolves_three_levels(self, deep_path) -> None:
        assert (deep_path / "^^^").resolve().path == deep_path.parent.parent.parent.path

    def test_caret_chain_clamps_at_root(self, deep_path) -> None:
        """Walking up past the root stops at the root."""
        deep_root = deep_path.parent.parent.parent
        assert (deep_path / "^^^^^").resolve().path == deep_root.path

    def test_resolve_with_no_carets_returns_self(self, deep_path) -> None:
        assert deep_path.resolve() is deep_path


class TestCaretMixedWithNames:
    def test_up_then_into_sibling_directory(self, deep_path) -> None:
        sibling = deep_path.parent.parent / _sibling_path_for(deep_path)
        joined = deep_path / f"^.^.{_sibling_path_for(deep_path)}"
        assert joined.resolve().path == sibling.path

    def test_consecutive_carets_then_name(self, deep_path) -> None:
        sibling = deep_path.parent.parent / _sibling_path_for(deep_path)
        joined = deep_path / f"^^.{_sibling_path_for(deep_path)}"
        assert joined.resolve().path == sibling.path

    def test_io_resolves_carets_transparently(self, deep_path) -> None:
        """I/O methods resolve ^ internally so the disc layer sees a clean path."""
        # deep_path is a file. Calling read_bytes on a path with carets
        # that resolves to the same file should succeed.
        joined = deep_path.parent / "^" / deep_path.parent.name / deep_path.name
        # joined = $.Games.^.Games.Elite -- resolves to $.Games.Elite
        assert joined.read_bytes() == deep_path.read_bytes()


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

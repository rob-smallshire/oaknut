"""Path objects retain pure-op behaviour after their handle closes.

The contract documented in ``api/patterns/paths.rst``:

- Pure path manipulation (slash-join, parent, name, parts, path,
  equality, str/repr) keeps working after the filesystem handle's
  ``with`` block exits — paths describe a location, not the bytes
  at that location.
- I/O operations (read_bytes, write_bytes, stat, iterdir, walk,
  exists, ...) raise :class:`oaknut.file.FilesystemClosedError`
  when the handle is closed.

Tested against all three concrete path classes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs import ADFS, ADFS_S
from oaknut.afs import AFS
from oaknut.dfs import DFS
from oaknut.file import FilesystemClosedError


def _dfs_closed_paths(tmp_path: Path):
    filepath = tmp_path / "demo.ssd"
    with DFS.create_file(filepath, title="X") as dfs:
        (dfs.root / "$" / "HELLO").write_bytes(b"hi")
    with DFS.from_file(filepath) as dfs:
        path = dfs.root / "$" / "HELLO"
    # `dfs` is closed now.
    return path


def _adfs_closed_paths(tmp_path: Path):
    filepath = tmp_path / "demo.adl"
    with ADFS.create_file(filepath, ADFS_S, title="X") as adfs:
        (adfs.root / "Hello").write_bytes(b"hi")
    with ADFS.from_file(filepath) as adfs:
        path = adfs.root / "Hello"
    return path


def _afs_closed_paths(tmp_path: Path):
    filepath = tmp_path / "server.dat"
    with AFS.create_file(filepath, capacity="5MB", disc_name="X") as afs:
        (afs.root / "Hello").write_bytes(b"hi")
    with AFS.from_file(filepath) as afs:
        path = afs.root / "Hello"
    return path


@pytest.fixture(
    params=[_dfs_closed_paths, _adfs_closed_paths, _afs_closed_paths],
    ids=["dfs", "adfs", "afs"],
)
def closed_path(request, tmp_path):
    return request.param(tmp_path)


class TestPureOpsSurviveClose:
    def test_str_still_works(self, closed_path) -> None:
        assert isinstance(str(closed_path), str) and str(closed_path)

    def test_name_still_works(self, closed_path) -> None:
        assert closed_path.name == "Hello" or closed_path.name == "HELLO"

    def test_parent_still_works(self, closed_path) -> None:
        # parent is a pure derivation — must succeed.
        p = closed_path.parent
        assert p is not None

    def test_parts_still_works(self, closed_path) -> None:
        assert isinstance(closed_path.parts, tuple)

    def test_path_property_still_works(self, closed_path) -> None:
        assert isinstance(closed_path.path, str)

    def test_slash_join_still_works(self, closed_path) -> None:
        sibling = closed_path.parent / "Other"
        assert sibling.name == "Other"

    def test_equality_still_works(self, closed_path) -> None:
        assert closed_path == closed_path
        assert closed_path != closed_path.parent


class TestIORaisesAfterClose:
    def test_read_bytes_raises(self, closed_path) -> None:
        with pytest.raises(FilesystemClosedError):
            closed_path.read_bytes()

    def test_exists_raises(self, closed_path) -> None:
        with pytest.raises(FilesystemClosedError):
            closed_path.exists()

    def test_stat_raises(self, closed_path) -> None:
        with pytest.raises(FilesystemClosedError):
            closed_path.stat()

    def test_iterdir_raises_on_parent(self, closed_path) -> None:
        with pytest.raises(FilesystemClosedError):
            list(closed_path.parent.iterdir())

    def test_walk_raises_on_parent(self, closed_path) -> None:
        with pytest.raises(FilesystemClosedError):
            list(closed_path.parent.walk())

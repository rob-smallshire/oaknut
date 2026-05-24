"""Every concrete path class conforms to the AcornPath base.

Cross-package conformance: DFSPath / ADFSPath / AFSPath all inherit
from :class:`oaknut.file.AcornPath`, share its uniform surface, and
behave consistently against shared smoke checks (touch, walk,
copy_to wiring, isinstance for type-hinting).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs import ADFS, ADFS_S
from oaknut.afs import AFS
from oaknut.dfs import DFS
from oaknut.file import AcornPath


def _dfs_path(tmp_path: Path):
    """Yield a writable DFSPath rooted in a fresh empty disc."""
    filepath = tmp_path / "demo.ssd"
    with DFS.create_file(filepath, title="X"):
        pass
    with DFS.from_file(filepath) as dfs:
        yield dfs.root / "$.HELLO"


def _adfs_path(tmp_path: Path):
    """Yield a writable ADFSPath inside a fresh empty floppy."""
    adfs = ADFS.create(ADFS_S)
    yield adfs.root / "Hello"


def _afs_path(tmp_path: Path):
    """Yield a writable AFSPath at the root of a fresh AFS server."""
    filepath = tmp_path / "server.dat"
    with AFS.create_file(filepath, capacity="5MB", disc_name="X"):
        pass
    with AFS.from_file(filepath) as afs:
        yield afs.root / "Hello"


@pytest.fixture(
    params=[_dfs_path, _adfs_path, _afs_path],
    ids=["dfs", "adfs", "afs"],
)
def path(request, tmp_path):
    yield from request.param(tmp_path)


class TestAcornPathConformance:
    def test_is_acornpath_instance(self, path: AcornPath) -> None:
        assert isinstance(path, AcornPath)

    def test_touch_creates_empty_file(self, path: AcornPath) -> None:
        path.touch()
        assert path.exists()
        assert path.read_bytes() == b""

    def test_touch_idempotent_with_exist_ok(self, path: AcornPath) -> None:
        path.write_bytes(b"keep me")
        path.touch()  # exist_ok=True by default
        assert path.read_bytes() == b"keep me"

    def test_read_text_round_trip(self, path: AcornPath) -> None:
        path.write_text("alpha\nbeta\n")
        assert path.read_text() == "alpha\nbeta\n"

    def test_iter_is_iterdir(self, path: AcornPath) -> None:
        parent = path.parent
        path.write_bytes(b"x")
        from_iter = sorted(p.name for p in parent)
        from_iterdir = sorted(p.name for p in parent.iterdir())
        assert from_iter == from_iterdir

    def test_walk_yields_pre_order_tuples(self, path: AcornPath) -> None:
        path.write_bytes(b"x")
        steps = list(path.parent.walk())
        # First step always describes `path.parent` itself.
        first_dir, _dirs, files = steps[0]
        assert first_dir == path.parent
        assert path.name in files

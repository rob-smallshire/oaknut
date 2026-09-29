"""The path APIs refuse to overwrite a locked file, like ``*SAVE``.

See issue #62: DFS raised a bare ``PermissionError`` (escaping the CLI as
a traceback), while ADFS and AFS silently replaced locked files.
"""

from __future__ import annotations

import pytest
from oaknut.adfs import ADFS, ADFS_S
from oaknut.adfs.exceptions import ADFSFileLockedError
from oaknut.afs import AFS
from oaknut.afs.exceptions import AFSFileLockedError
from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS
from oaknut.dfs.exceptions import FileLocked
from oaknut.file import FSError


def test_dfs_write_over_locked_raises_file_locked(tmp_path):
    with DFS.create_file(tmp_path / "d.ssd", ACORN_DFS_80T_SINGLE_SIDED, title="T") as dfs:
        path = dfs.root / "$" / "F"
        path.write_bytes(b"original")
        path.lock()
        with pytest.raises(FileLocked):
            path.write_bytes(b"replacement")
        assert path.read_bytes() == b"original"


def test_dfs_file_locked_is_still_a_permission_error():
    # Existing callers catching PermissionError keep working.
    assert issubclass(FileLocked, PermissionError)
    assert issubclass(FileLocked, FSError)


def test_adfs_write_over_locked_raises():
    adfs = ADFS.create(ADFS_S)
    path = adfs.root / "F"
    path.write_bytes(b"original")
    path.lock()
    with pytest.raises(ADFSFileLockedError):
        path.write_bytes(b"replacement")
    assert path.read_bytes() == b"original"


def test_afs_write_over_locked_raises(tmp_path):
    with AFS.create_file(tmp_path / "s.dat", capacity="5MB", disc_name="S") as afs:
        path = afs.root / "F"
        path.write_bytes(b"original")
        path.lock()
        with pytest.raises(AFSFileLockedError):
            path.write_bytes(b"replacement")
        assert path.read_bytes() == b"original"

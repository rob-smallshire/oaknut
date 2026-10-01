"""DFS directories named by characters other than ``$`` and ``A``–``Z`` (#46).

A DFS catalogue entry's directory is any character, not only ``$`` or a
letter: Acorn's Econet Level 1 utilities disc keeps files under ``&``.
Listing must name such a directory in a way lookup resolves again.

The catalogue is built from scratch: an ordinary ``$`` file whose
directory byte (byte 7 of its sector-0 entry) is then rewritten.
"""

from __future__ import annotations

import pytest
from oaknut.dfs.dfs import DFS
from oaknut.dfs.formats import ACORN_DFS_40T_SINGLE_SIDED

_LOCK_BIT = 0x80


def _blank_buffer() -> bytearray:
    buffer = bytearray(102400)
    buffer[0:8] = b"TITLE   "
    buffer[256:260] = b"    "
    buffer[263] = 200
    return buffer


def _dfs_with_file_in(directory: str) -> DFS:
    """A DFS whose one file, PROT, lives in *directory*."""
    buffer = _blank_buffer()
    dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)
    (dfs.root / "$" / "PROT").write_bytes(b"data", load_address=0x1900, exec_address=0x8023)
    buffer[8 + 7] = (buffer[8 + 7] & _LOCK_BIT) | ord(directory)
    return DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)


@pytest.mark.parametrize("directory", ["&"])
class TestNonLetterDirectory:
    def test_the_catalogue_reads_the_directory(self, directory):
        dfs = _dfs_with_file_in(directory)
        assert [(f.directory, f.filename) for f in dfs.files] == [(directory, "PROT")]

    def test_the_root_lists_it_as_a_directory(self, directory):
        dfs = _dfs_with_file_in(directory)
        (child,) = dfs.path("").iterdir()
        assert child.path == directory
        assert child.is_dir()
        assert child.stat().is_directory

    def test_the_directory_lists_its_file(self, directory):
        dfs = _dfs_with_file_in(directory)
        assert [child.path for child in dfs.path(directory).iterdir()] == [f"{directory}.PROT"]

    def test_the_file_reads_back(self, directory):
        dfs = _dfs_with_file_in(directory)
        path = dfs.path(f"{directory}.PROT")
        assert path.read_bytes() == b"data"
        assert path.stat().load_address == 0x1900

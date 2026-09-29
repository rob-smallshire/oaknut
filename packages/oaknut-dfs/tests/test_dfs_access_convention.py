"""Tests for the Acorn DFS access convention."""

from __future__ import annotations

import pytest
from oaknut.dfs import ACORN_DFS_ACCESS, AcornDFSAccessConvention
from oaknut.file import DIRECTORY_CONTEXT, Access, AccessConvention


def test_is_an_access_convention():
    assert isinstance(ACORN_DFS_ACCESS, AcornDFSAccessConvention)
    assert isinstance(ACORN_DFS_ACCESS, AccessConvention)
    assert ACORN_DFS_ACCESS.name == "acorn-dfs"


@pytest.mark.parametrize(
    ("locked", "expected"),
    [
        (False, Access.R | Access.W),
        # Should be L|R: the DFS lock bit also means read-only — #57.
        (True, Access.L | Access.R | Access.W),
    ],
)
def test_to_canonical(locked, expected):
    assert ACORN_DFS_ACCESS.to_canonical(locked) == expected


@pytest.mark.parametrize(
    ("access", "locked"),
    [
        (Access(0x00), False),
        (Access(0x03), False),
        (Access(0x08), True),
        (Access(0x09), True),
        (Access(0x0B), True),
        (Access(0x33), False),
        (Access(0x19), True),
        # Only the lock bit is kept: dfsAttr = attr AND &08.
        (Access(0x02), False),
    ],
)
def test_from_canonical_keeps_only_the_lock_bit(access, locked):
    assert ACORN_DFS_ACCESS.from_canonical(access) is locked


def test_directories_read_the_same_way():
    assert ACORN_DFS_ACCESS.to_canonical(False, DIRECTORY_CONTEXT) == Access.R | Access.W


def test_every_value_settles_within_representable():
    for value in range(0x80):
        settled = ACORN_DFS_ACCESS.settle(Access(value))
        assert settled & ~ACORN_DFS_ACCESS.representable == Access(0)

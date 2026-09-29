"""Tests for the ROMFS access convention."""

from __future__ import annotations

import pytest
from oaknut.file import Access, AccessConvention
from oaknut.romfs import ACORN_ROMFS_ACCESS, AcornROMFSAccessConvention


def test_is_an_access_convention():
    assert isinstance(ACORN_ROMFS_ACCESS, AcornROMFSAccessConvention)
    assert isinstance(ACORN_ROMFS_ACCESS, AccessConvention)
    assert ACORN_ROMFS_ACCESS.name == "acorn-romfs"


@pytest.mark.parametrize(
    ("run_only", "expected"),
    [
        # An ordinary file is readable; a run-only one is E without R.
        (False, Access.R),
        (True, Access.E),
    ],
)
def test_to_canonical(run_only, expected):
    assert ACORN_ROMFS_ACCESS.to_canonical(run_only) == expected


@pytest.mark.parametrize(
    ("access", "run_only"),
    [
        (Access(0), False),
        (Access.R, False),
        (Access.E, True),
        (Access.E | Access.L, True),
        # Readable means loadable, so not run-only.
        (Access.E | Access.R, False),
        # The disc filing systems' delete-lock is not run-only: a locked
        # DFS file (LR) copied onto a ROM must stay loadable.
        (Access.L | Access.R, False),
        (Access.LWR, False),
        # Bit 6 is public execute in the Acorn byte, not run-only.
        (Access(0x40), False),
    ],
)
def test_from_canonical(access, run_only):
    assert ACORN_ROMFS_ACCESS.from_canonical(access) is run_only

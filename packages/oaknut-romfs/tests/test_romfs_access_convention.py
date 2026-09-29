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
        # An ordinary ROMFS file reads as no access (#60 step 4).
        (False, Access(0)),
        (True, Access.X),
    ],
)
def test_to_canonical(run_only, expected):
    assert ACORN_ROMFS_ACCESS.to_canonical(run_only) == expected


@pytest.mark.parametrize(
    ("access", "run_only"),
    [
        (Access(0), False),
        (Access.X, True),
        (Access.X | Access.R, True),
        # The disc filing systems' delete-lock is not run-only.
        (Access.LWR, False),
    ],
)
def test_from_canonical(access, run_only):
    assert ACORN_ROMFS_ACCESS.from_canonical(access) is run_only

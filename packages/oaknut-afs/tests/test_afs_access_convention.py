"""Tests for the AFS access convention."""

from __future__ import annotations

import pytest
from oaknut.afs import AFS_ACCESS, AFSAccess, AFSAccessConvention
from oaknut.file import DIRECTORY_CONTEXT, Access, AccessConvention


def test_is_an_access_convention():
    assert isinstance(AFS_ACCESS, AFSAccessConvention)
    assert isinstance(AFS_ACCESS, AccessConvention)
    assert AFS_ACCESS.name == "afs"


@pytest.mark.parametrize(
    ("afs", "canonical"),
    [
        ("WR/", 0x03),
        ("WR/R", 0x13),
        ("LR/R", 0x19),
        ("WR/WR", 0x33),
        ("LWR/", 0x0B),
        ("/", 0x00),
        # The directory bit is the object's type, not its access.
        ("DL/", 0x08),
    ],
)
def test_to_canonical(afs, canonical):
    assert AFS_ACCESS.to_canonical(AFSAccess.from_string(afs)) == Access(canonical)


def test_from_canonical_drops_execute():
    assert AFS_ACCESS.from_canonical(Access(0x07)) == AFSAccess.from_string("WR/")


def test_from_canonical_marks_directories_from_context():
    assert AFS_ACCESS.from_canonical(Access.L, DIRECTORY_CONTEXT) == AFSAccess.from_string("DL/")
    assert not AFS_ACCESS.from_canonical(Access.L).is_directory


def test_afs_access_translation_methods_agree():
    for value in range(0x40):
        access = Access(value)
        assert AFSAccess.from_acorn(access) == AFS_ACCESS.from_canonical(access)
    for byte in range(0x40):
        native = AFSAccess.from_byte(byte)
        assert native.to_acorn() == AFS_ACCESS.to_canonical(native)

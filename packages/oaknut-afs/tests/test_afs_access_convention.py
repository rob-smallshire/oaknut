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


def test_replacing_a_file_without_access_keeps_its_access():
    # The ROM preserves a file's access when it is replaced (#63).
    from helpers.afs_image import build_synthetic_adfs_with_afs

    afs = build_synthetic_adfs_with_afs().afs_partition
    path = afs.root / "Shared"
    path.write_bytes(b"one", access=AFSAccess.from_string("WR/R"))
    path.write_bytes(b"two")
    assert path.read_bytes() == b"two"
    assert path.stat().access == Access(0x13)


def test_a_new_file_without_access_gets_the_default():
    from helpers.afs_image import build_synthetic_adfs_with_afs

    afs = build_synthetic_adfs_with_afs().afs_partition
    (afs.root / "Fresh").write_bytes(b"x")
    assert (afs.root / "Fresh").stat().access == Access(0x03)  # WR/, the ROM's ACCDEF

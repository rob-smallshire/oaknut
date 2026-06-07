"""AFS write paths must never put two entries of one name in a directory.

AFS already overwrites a file written twice and rejects mkdir/rename
clashes; these tests lock that in, fix the file-over-directory case
(which silently replaced the directory), and add the no-duplicate-names
post-condition to the directory-mutation primitives as a backstop.
"""

import datetime

import pytest
from oaknut.adfs import ADFS, ADFS_L
from oaknut.afs.access import AFSAccess
from oaknut.afs.directory import (
    DirectoryEntry,
    _assert_no_duplicate_entries,
    build_directory_bytes,
)
from oaknut.afs.exceptions import AFSDirectoryEntryExistsError, AFSPathError
from oaknut.afs.types import AfsDate, SystemInternalName
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, initialise


def _fresh_afs():
    adfs = ADFS.create(ADFS_L)
    initialise(
        adfs,
        spec=InitSpec(disc_name="AFS", size=AFSSizeSpec.cylinders(20), users=[]),
    )
    return adfs.afs_partition


def _names(directory):
    return sorted(e.name for e in directory)


class TestAfsWritePathsRejectDuplicates:
    def test_rewriting_a_file_overwrites_not_duplicates(self):
        afs = _fresh_afs()
        (afs.root / "FILE").write_bytes(b"first")
        (afs.root / "FILE").write_bytes(b"second")
        assert [e.name for e in afs.root if e.name == "FILE"] == ["FILE"]
        assert (afs.root / "FILE").read_bytes() == b"second"

    def test_mkdir_over_existing_directory_raises(self):
        afs = _fresh_afs()
        (afs.root / "DIR").mkdir()
        with pytest.raises(AFSDirectoryEntryExistsError):
            (afs.root / "DIR").mkdir()

    def test_mkdir_over_existing_file_raises(self):
        afs = _fresh_afs()
        (afs.root / "X").write_bytes(b"f")
        with pytest.raises(AFSPathError):
            (afs.root / "X").mkdir()

    def test_rename_onto_existing_name_raises(self):
        afs = _fresh_afs()
        (afs.root / "AAA").write_bytes(b"a")
        (afs.root / "BBB").write_bytes(b"b")
        with pytest.raises(AFSDirectoryEntryExistsError):
            (afs.root / "AAA").rename(afs.root / "BBB")

    def test_write_over_existing_directory_raises(self):
        afs = _fresh_afs()
        (afs.root / "D").mkdir()
        with pytest.raises(AFSPathError):
            (afs.root / "D").write_bytes(b"f")


class TestAfsDirectoryPostCondition:
    def test_duplicate_entries_trip_the_assertion(self):
        def entry(name, sin):
            return DirectoryEntry(
                name=name,
                load_address=0,
                exec_address=0,
                access=AFSAccess.from_string("R/R"),
                date=AfsDate(datetime.date(2026, 4, 11)),
                sin=SystemInternalName(sin),
            )

        raw = build_directory_bytes(
            name="$",
            master_sequence_number=1,
            entries=[entry("SAME", 0x200), entry("SAME", 0x201)],
            size_in_bytes=512,
        )
        with pytest.raises(AssertionError, match="duplicate entries"):
            _assert_no_duplicate_entries(raw)

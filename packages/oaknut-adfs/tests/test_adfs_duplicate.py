"""ADFS write paths must never put two entries of one name in a directory.

ADFS already overwrites a file written twice and rejects mkdir/file
clashes; these tests lock that in, and add the no-duplicate-names
post-condition as a backstop (the sorted-order assertion alone permits
equal — i.e. duplicate — names).
"""

import pytest
from oaknut.adfs import ADFS, ADFS_S
from oaknut.adfs.adfs import _assert_entries_sorted
from oaknut.adfs.exceptions import ADFSEntryExistsError, ADFSPathError


def _names(directory):
    return [entry.name for entry in directory]


class TestAdfsWritePathsRejectDuplicates:
    def test_rewriting_a_file_overwrites_not_duplicates(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "FILE").write_bytes(b"first")
        (adfs.root / "FILE").write_bytes(b"second")
        assert _names(adfs.root) == ["FILE"]
        assert (adfs.root / "FILE").read_bytes() == b"second"

    def test_mkdir_over_existing_directory_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "DIR").mkdir()
        with pytest.raises(ADFSEntryExistsError):
            (adfs.root / "DIR").mkdir()

    def test_mkdir_over_existing_file_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "X").write_bytes(b"f")
        with pytest.raises(ADFSEntryExistsError):
            (adfs.root / "X").mkdir()

    def test_write_over_existing_directory_raises(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "D").mkdir()
        with pytest.raises(ADFSPathError):
            (adfs.root / "D").write_bytes(b"f")


class TestAdfsDirectoryPostCondition:
    def test_duplicate_entries_trip_the_assertion(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "X").write_bytes(b"d")
        entry = adfs._read_root_directory().entries[0]
        with pytest.raises(AssertionError, match="duplicate entries"):
            _assert_entries_sorted((entry, entry))

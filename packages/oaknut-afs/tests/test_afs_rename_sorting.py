"""A same-directory AFS rename must keep the in-use list alphabetical.

AFS resolves names by walking the directory's in-use list, which the
server keeps in alphabetical order. The low-level ``rename_entry`` is a
ROM-faithful in-place slot rewrite that can leave the list un-ordered;
the high-level ``AFSPath.rename`` must not — it deletes and re-inserts so
the renamed entry lands at its new sorted position.
"""

import pytest
from oaknut.adfs import ADFS, ADFS_L
from oaknut.afs.directory import (
    _assert_entries_sorted,
    build_directory_bytes,
    rename_entry,
)
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, initialise


def _fresh_afs():
    adfs = ADFS.create(ADFS_L)
    initialise(
        adfs,
        spec=InitSpec(disc_name="AFS", size=AFSSizeSpec.cylinders(20), users=[]),
    )
    return adfs.afs_partition


def _upper_sorted(names):
    return sorted(names, key=str.upper)


class TestAfsRenameKeepsSorted:
    def test_rename_to_later_name_resorts(self):
        afs = _fresh_afs()
        (afs.root / "AAA").write_bytes(b"a")
        (afs.root / "MMM").write_bytes(b"m")
        (afs.root / "AAA").rename(afs.root / "ZZZ")
        names = [e.name for e in afs.root]
        assert names == _upper_sorted(names)
        assert "ZZZ" in names and "AAA" not in names
        assert (afs.root / "ZZZ").read_bytes() == b"a"

    def test_rename_to_earlier_name_resorts(self):
        afs = _fresh_afs()
        (afs.root / "MMM").write_bytes(b"m")
        (afs.root / "NNN").write_bytes(b"n")
        (afs.root / "NNN").rename(afs.root / "AAA")
        names = [e.name for e in afs.root]
        assert names == _upper_sorted(names)
        assert (afs.root / "AAA").read_bytes() == b"n"


class TestAfsDirectorySortPostCondition:
    def test_unordered_in_use_list_trips_the_assertion(self):
        # rename_entry is the ROM-faithful in-place primitive; using it to
        # move a name past its sort position yields an un-ordered list that
        # the post-condition must reject.
        import datetime

        from oaknut.afs.access import AFSAccess
        from oaknut.afs.directory import DirectoryEntry
        from oaknut.afs.types import AfsDate, SystemInternalName

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
            entries=[entry("Alpha", 0x200), entry("Beta", 0x201)],
            size_in_bytes=512,
        )
        unordered = rename_entry(raw, "Alpha", "Zulu")
        with pytest.raises(AssertionError, match="out of order"):
            _assert_entries_sorted(unordered)

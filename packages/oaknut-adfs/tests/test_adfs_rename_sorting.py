"""Renaming must keep the directory in sorted order.

ADFS directories must be sorted ascending by name — the ROM looks files
up with a linear scan that terminates early — so a rename that changes
where an entry sorts has to move it, not just relabel it in place. The
same applies to a cross-directory move: the entry must land in sorted
position in its new directory.
"""

from oaknut.adfs import ADFS, ADFS_M


def _names(directory):
    return [entry.name for entry in directory]


class TestRenameKeepsSorted:
    def test_rename_to_later_name_resorts(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "AAA").write_bytes(b"a")
        (adfs.root / "BBB").write_bytes(b"b")
        (adfs.root / "AAA").rename(adfs.root / "ZZZ")
        assert _names(adfs.root) == ["BBB", "ZZZ"]
        assert (adfs.root / "ZZZ").read_bytes() == b"a"

    def test_rename_to_earlier_name_resorts(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "MMM").write_bytes(b"m")
        (adfs.root / "NNN").write_bytes(b"n")
        (adfs.root / "NNN").rename(adfs.root / "AAA")
        assert _names(adfs.root) == ["AAA", "MMM"]
        assert (adfs.root / "AAA").read_bytes() == b"n"

    def test_renamed_entry_is_findable(self):
        # A linear scan with early termination would miss an out-of-order
        # entry, so prove the renamed file is actually reachable.
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "AAA").write_bytes(b"a")
        (adfs.root / "BBB").write_bytes(b"b")
        (adfs.root / "AAA").rename(adfs.root / "ZZZ")
        assert (adfs.root / "ZZZ").exists()
        assert not (adfs.root / "AAA").exists()


class TestCrossDirectoryMoveKeepsSorted:
    def test_move_into_directory_sorts(self):
        adfs = ADFS.create(ADFS_M)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir" / "Beta").write_bytes(b"beta")
        (adfs.root / "Dir" / "Gamma").write_bytes(b"gamma")
        (adfs.root / "Alpha").write_bytes(b"alpha")
        (adfs.root / "Alpha").rename(adfs.root / "Dir" / "Alpha")
        assert _names(adfs.root / "Dir") == ["Alpha", "Beta", "Gamma"]
        assert (adfs.root / "Dir" / "Alpha").read_bytes() == b"alpha"

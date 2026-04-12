"""Tests for sorted directory entry insertion.

ADFS old-format directories require entries in ascending ASCII
order (case-insensitive, bit 7 stripped). The ROM uses binary
search for file lookup, so unsorted entries are not found.
"""

from oaknut.adfs import ADFS, ADFS_S


class TestDirectoryEntrySorted:
    def test_entries_sorted_after_multiple_writes(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Zebra").write_bytes(b"z")
        (adfs.root / "Apple").write_bytes(b"a")
        (adfs.root / "Mango").write_bytes(b"m")

        names = [e.name for e in adfs.root.iterdir()]
        assert names == sorted(names, key=str.upper)

    def test_bang_boot_before_letters(self):
        """!BOOT (0x21) must sort before alphabetic characters."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "FS3v126").write_bytes(b"fs")
        (adfs.root / "!BOOT").write_bytes(b"boot")

        names = [e.name for e in adfs.root.iterdir()]
        assert names[0] == "!BOOT"
        assert names[1] == "FS3v126"

    def test_sorted_after_delete_and_reinsert(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Beta").write_bytes(b"b")
        (adfs.root / "Alpha").write_bytes(b"a")
        (adfs.root / "Gamma").write_bytes(b"g")

        (adfs.root / "Beta").unlink()
        (adfs.root / "Delta").write_bytes(b"d")

        names = [e.name for e in adfs.root.iterdir()]
        assert names == sorted(names, key=str.upper)

    def test_case_insensitive_sort(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "alpha").write_bytes(b"a")
        (adfs.root / "BETA").write_bytes(b"b")
        (adfs.root / "gamma").write_bytes(b"g")

        names = [e.name for e in adfs.root.iterdir()]
        assert names == ["alpha", "BETA", "gamma"]

    def test_mkdir_sorted(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Zdir").mkdir()
        (adfs.root / "Afile").write_bytes(b"a")

        names = [e.name for e in adfs.root.iterdir()]
        assert names[0] == "Afile"
        assert names[1] == "Zdir"

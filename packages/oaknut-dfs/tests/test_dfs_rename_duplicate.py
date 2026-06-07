"""Renaming a DFS file onto an existing name must not corrupt the catalogue.

DFS looks files up by name, so two entries sharing a name leaves one
unreachable. The catalogue therefore asserts the no-duplicates
post-condition after a rename, and the rename refuses an existing
destination up front with a friendly error.
"""

import pytest
from oaknut.dfs.dfs import DFS
from oaknut.dfs.exceptions import FileExistsError as DFSFileExistsError
from oaknut.dfs.formats import ACORN_DFS_40T_SINGLE_SIDED


def _make_empty_dfs():
    buffer = bytearray(102400)
    buffer[0:8] = b"TESTDISC"
    buffer[256:260] = b"    "
    buffer[263] = 200
    return DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)


def _dfs_with_two_files():
    dfs = _make_empty_dfs()
    (dfs.root / "$" / "AAA").write_bytes(b"aaa", load_address=0x1900)
    (dfs.root / "$" / "BBB").write_bytes(b"bbb", load_address=0x2000)
    return dfs


class TestRenamePostCondition:
    def test_impl_creating_a_duplicate_trips_the_assertion(self):
        # The unguarded primitive would relabel AAA as BBB while BBB still
        # exists; the post-condition assertion is the safety net that
        # catches that catalogue corruption.
        dfs = _dfs_with_two_files()
        catalogue = dfs._catalogued_surface.catalogue
        catalogue._rename_file_impl("$.AAA", "$.BBB")
        with pytest.raises(AssertionError, match="duplicate entries"):
            catalogue._assert_no_duplicate_entries()


class TestRenameGuard:
    def test_rename_onto_existing_name_is_refused(self):
        dfs = _dfs_with_two_files()
        with pytest.raises(DFSFileExistsError):
            (dfs.root / "$" / "AAA").rename(dfs.root / "$" / "BBB")

    def test_refused_rename_leaves_catalogue_intact(self):
        dfs = _dfs_with_two_files()
        with pytest.raises(DFSFileExistsError):
            (dfs.root / "$" / "AAA").rename(dfs.root / "$" / "BBB")
        assert (dfs.root / "$" / "AAA").read_bytes() == b"aaa"
        assert (dfs.root / "$" / "BBB").read_bytes() == b"bbb"
        names = sorted(entry.name for entry in (dfs.root / "$"))
        assert names == ["AAA", "BBB"]

    def test_plain_rename_still_works(self):
        dfs = _dfs_with_two_files()
        (dfs.root / "$" / "AAA").rename(dfs.root / "$" / "CCC")
        assert (dfs.root / "$" / "CCC").read_bytes() == b"aaa"
        assert not (dfs.root / "$" / "AAA").exists()


class TestWatfordCatalogueSharesTheGuard:
    """The guard and post-condition live on the base Catalogue, so the
    Watford catalogue inherits them too (template-method)."""

    def _watford(self, tmp_path):
        from oaknut.dfs.formats import WATFORD_DFS_80T_SINGLE_SIDED

        image_filepath = tmp_path / "w.ssd"
        return DFS.create_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED, title="W")

    def test_rewriting_a_file_overwrites_not_duplicates(self, tmp_path):
        with self._watford(tmp_path) as dfs:
            (dfs.root / "$" / "AAA").write_bytes(b"first")
            (dfs.root / "$" / "AAA").write_bytes(b"second")
            assert [e.name for e in (dfs.root / "$")] == ["AAA"]
            assert (dfs.root / "$" / "AAA").read_bytes() == b"second"

    def test_rename_onto_existing_name_is_refused(self, tmp_path):
        with self._watford(tmp_path) as dfs:
            (dfs.root / "$" / "AAA").write_bytes(b"a")
            (dfs.root / "$" / "BBB").write_bytes(b"b")
            with pytest.raises(DFSFileExistsError):
                (dfs.root / "$" / "AAA").rename(dfs.root / "$" / "BBB")

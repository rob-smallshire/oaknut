"""Cross-filesystem :class:`oaknut.file.Stat` protocol conformance.

Asserts that the ``stat()`` result from each path class (DFSPath,
ADFSPath, AFSPath) exposes the uniform fields documented by
:class:`oaknut.file.Stat`. Lets portable code iterate across
filesystems without per-family branching.

Regression cover for issue #26.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs import ADFS
from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS
from oaknut.file import Access, Stat


@pytest.fixture
def dfs_stat(dfs_image_filepath: Path):
    with DFS.from_file(dfs_image_filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
        return (dfs.root / "$.Hello").stat()


@pytest.fixture
def adfs_stat(adfs_image_filepath: Path):
    with ADFS.from_file(adfs_image_filepath) as adfs:
        return (adfs.root / "Hello").stat()


@pytest.fixture
def afs_stat(afs_image_filepath: Path):
    with ADFS.from_file(afs_image_filepath) as adfs:
        afs = adfs.afs_partition
        return (afs.root / "Greeting").stat()


class TestStatProtocolConformance:
    @pytest.mark.parametrize("fixture_name", ["dfs_stat", "adfs_stat", "afs_stat"])
    def test_required_fields_present(self, request, fixture_name: str) -> None:
        st = request.getfixturevalue(fixture_name)
        assert hasattr(st, "length")
        assert hasattr(st, "load_address")
        assert hasattr(st, "exec_address")
        assert hasattr(st, "access")
        assert hasattr(st, "is_directory")
        assert hasattr(st, "date")

    @pytest.mark.parametrize("fixture_name", ["dfs_stat", "adfs_stat", "afs_stat"])
    def test_isinstance_stat(self, request, fixture_name: str) -> None:
        st = request.getfixturevalue(fixture_name)
        assert isinstance(st, Stat)

    @pytest.mark.parametrize("fixture_name", ["dfs_stat", "adfs_stat", "afs_stat"])
    def test_access_is_canonical_Access(self, request, fixture_name: str) -> None:
        st = request.getfixturevalue(fixture_name)
        assert isinstance(st.access, Access), (
            f"{fixture_name}.access is {type(st.access).__name__}, expected Access"
        )

    @pytest.mark.parametrize("fixture_name", ["dfs_stat", "adfs_stat", "afs_stat"])
    def test_length_is_nonnegative_int(self, request, fixture_name: str) -> None:
        st = request.getfixturevalue(fixture_name)
        assert isinstance(st.length, int)
        assert st.length >= 0

    @pytest.mark.parametrize("fixture_name", ["dfs_stat", "adfs_stat", "afs_stat"])
    def test_is_directory_false_for_regular_file(
        self, request, fixture_name: str
    ) -> None:
        st = request.getfixturevalue(fixture_name)
        assert st.is_directory is False


class TestDFSStatExtras:
    def test_locked_unlocked_file_has_RW_access(self, dfs_image_filepath: Path) -> None:
        with DFS.from_file(dfs_image_filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            st = (dfs.root / "$.Hello").stat()
        # DFS files are implicitly owner R+W; no L bit when unlocked.
        assert st.access == Access.R | Access.W

    def test_dfs_date_is_none(self, dfs_image_filepath: Path) -> None:
        with DFS.from_file(dfs_image_filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            st = (dfs.root / "$.Hello").stat()
        assert st.date is None


class TestADFSStatExtras:
    def test_default_write_access_is_WR_R(self, adfs_image_filepath: Path) -> None:
        with ADFS.from_file(adfs_image_filepath) as adfs:
            st = (adfs.root / "Hello").stat()
        # ADFS write_bytes default is WR/R = R | W | PR.
        assert st.access & Access.R
        assert st.access & Access.W
        assert st.access & Access.PR


class TestAFSStatExtras:
    def test_afs_stat_exposes_raw_afs_access(self, afs_image_filepath: Path) -> None:
        from oaknut.afs import AFSAccess

        with ADFS.from_file(afs_image_filepath) as adfs:
            afs = adfs.afs_partition
            st = (afs.root / "Greeting").stat()
        # AFS extra field surviving the protocol uniformisation.
        assert isinstance(st.afs_access, AFSAccess)

    def test_afs_stat_canonical_access_matches_afs_access(
        self, afs_image_filepath: Path
    ) -> None:
        with ADFS.from_file(afs_image_filepath) as adfs:
            afs = adfs.afs_partition
            st = (afs.root / "Greeting").stat()
        # The canonical Access view must equal the on-disc byte translated
        # to wire form — that's the whole point of the protocol field.
        assert st.access == st.afs_access.to_acorn()

    def test_directory_entry_still_reachable(self, afs_image_filepath: Path) -> None:
        from oaknut.afs.directory import DirectoryEntry

        with ADFS.from_file(afs_image_filepath) as adfs:
            afs = adfs.afs_partition
            entry = (afs.root / "Greeting").directory_entry()
        assert isinstance(entry, DirectoryEntry)
        # The sin field is AFS-only and lives on DirectoryEntry, not on
        # the unified AFSStat surface.
        assert hasattr(entry, "sin")

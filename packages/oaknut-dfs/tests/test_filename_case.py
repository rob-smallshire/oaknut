"""DFS preserves filename case on write, matching case-insensitively.

The DFS ROM stores a name verbatim — the catalogue copy loop writes the
parsed bytes unchanged, and *RENAME explicitly allows a same-entry "case
change" (DFS 2.24 disassembly) — and folds case only when *comparing*
names (``AND #&5F``). So oaknut must record the case the caller gave and
fold only on lookup, not upper-case names into the catalogue.
"""

import pytest
from oaknut.dfs.dfs import DFS
from oaknut.dfs.formats import (
    ACORN_DFS_80T_SINGLE_SIDED,
    WATFORD_DFS_80T_SINGLE_SIDED,
)

FORMATS = [
    pytest.param(ACORN_DFS_80T_SINGLE_SIDED, id="acorn"),
    pytest.param(WATFORD_DFS_80T_SINGLE_SIDED, id="watford"),
]


class TestCaseIsPreserved:
    @pytest.mark.parametrize("disc_format", FORMATS)
    def test_mixed_case_name_stored_verbatim(self, disc_format):
        dfs = DFS.create(disc_format)
        dfs.path("$.Hello").write_bytes(b"x")
        stored = {entry.filename for entry in dfs.files}
        assert "Hello" in stored
        assert "HELLO" not in stored

    @pytest.mark.parametrize("disc_format", FORMATS)
    def test_lower_case_name_stays_lower(self, disc_format):
        dfs = DFS.create(disc_format)
        dfs.path("$.boot").write_bytes(b"x")
        assert "boot" in {entry.filename for entry in dfs.files}


class TestDirectoryCase:
    """Single-letter directories behave like filenames: case-preserving on
    store, case-insensitive on match (``$`` has no case)."""

    @pytest.mark.parametrize("disc_format", FORMATS)
    def test_directory_letter_case_preserved(self, disc_format):
        dfs = DFS.create(disc_format)
        dfs.path("b.Game").write_bytes(b"x")
        entry = next(e for e in dfs.files if e.filename == "Game")
        assert entry.directory == "b"

    @pytest.mark.parametrize("disc_format", FORMATS)
    def test_directory_matched_case_insensitively(self, disc_format):
        dfs = DFS.create(disc_format)
        dfs.path("b.Game").write_bytes(b"data")
        assert dfs.path("B.Game").read_bytes() == b"data"

    @pytest.mark.parametrize("disc_format", FORMATS)
    def test_directory_navigation_folds_case(self, disc_format):
        dfs = DFS.create(disc_format)
        dfs.path("b.Game").write_bytes(b"x")
        # A directory stored lower-case is reachable under either case.
        assert (dfs.root / "B").exists()
        assert (dfs.root / "b").exists()
        assert "Game" in [p.name for p in (dfs.root / "B").iterdir()]


class TestLookupIsCaseInsensitive:
    @pytest.mark.parametrize("disc_format", FORMATS)
    def test_found_under_any_case(self, disc_format):
        dfs = DFS.create(disc_format)
        dfs.path("$.Hello").write_bytes(b"data")
        assert dfs.path("$.HELLO").read_bytes() == b"data"
        assert dfs.path("$.hello").read_bytes() == b"data"
        assert dfs.path("$.Hello").read_bytes() == b"data"

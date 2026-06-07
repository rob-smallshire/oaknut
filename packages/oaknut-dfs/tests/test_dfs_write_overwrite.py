"""Writing over an existing DFS file overwrites it rather than duplicating.

DFS *SAVE onto an existing name replaces the file. Adding a second
catalogue entry with the same name instead leaves one copy unreachable,
so the write path removes any existing entry first and the catalogue
asserts the no-duplicates post-condition after every add.
"""

import pytest
from oaknut.dfs.dfs import DFS
from oaknut.dfs.formats import ACORN_DFS_40T_SINGLE_SIDED


def _make_empty_dfs():
    buffer = bytearray(102400)
    buffer[0:8] = b"TESTDISC"
    buffer[256:260] = b"    "
    buffer[263] = 200
    return DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)


class TestWriteOverwrites:
    def test_rewriting_a_file_overwrites_not_duplicates(self):
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "HELLO").write_bytes(b"first", load_address=0x1900)
        (dfs.root / "$" / "HELLO").write_bytes(b"second", load_address=0x2000)
        names = [entry.name for entry in (dfs.root / "$")]
        assert names == ["HELLO"]
        assert (dfs.root / "$" / "HELLO").read_bytes() == b"second"


class TestAddPostCondition:
    def test_add_impl_creating_a_duplicate_trips_the_assertion(self):
        # The unguarded primitive can add a second entry with an existing
        # name; the post-condition assertion is the backstop that catches
        # the resulting catalogue corruption.
        dfs = _make_empty_dfs()
        (dfs.root / "$" / "HELLO").write_bytes(b"data", load_address=0x1900)
        catalogue = dfs._catalogued_surface.catalogue
        catalogue._add_file_entry_impl(
            filename="HELLO",
            directory="$",
            load_address=0,
            exec_address=0,
            length=4,
            start_sector=50,
        )
        with pytest.raises(AssertionError, match="duplicate entries"):
            catalogue._assert_no_duplicate_entries()

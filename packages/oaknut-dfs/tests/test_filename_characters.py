"""Filename character policy for DFS writes.

DFS forbids ``#``, ``*`` and a non-leading ``!`` only at the *command
line*, where they are wildcards or syntax. The on-disc catalogue stores
those bytes in its seven-byte name field perfectly well, and real discs
rely on it — the game Guardian ships ``GUARD#1`` / ``GUARD#2`` as light
copy-protection, unreachable from ``*DELETE`` yet loaded by name through
OSFILE.

So oaknut is liberal on the storage layer: a write may create a name
containing a wildcard metacharacter, and a read never refuses one. Only
constraints the *format* genuinely cannot represent stay hard errors —
over-length, control characters, and top-bit-set bytes outside the
seven-bit name field.
"""

import pytest
from oaknut.dfs.dfs import DFS
from oaknut.dfs.formats import (
    ACORN_DFS_80T_SINGLE_SIDED,
    WATFORD_DFS_80T_SINGLE_SIDED,
)

# Both flat-catalogue DFS variants share the relaxed policy; each has its
# own validate_filename, so exercise both.
FORMATS = [
    pytest.param(ACORN_DFS_80T_SINGLE_SIDED, id="acorn"),
    pytest.param(WATFORD_DFS_80T_SINGLE_SIDED, id="watford"),
]

# Names a faithful tool must let you create — the wildcard/syntax
# metacharacters the command line cannot easily reach.
STORABLE_NAMES = [
    pytest.param("GUARD#1", id="hash-single"),
    pytest.param("GUARD#2", id="hash-other"),
    pytest.param("SAVE*", id="star"),
    pytest.param("DATA!1", id="bang-mid"),
]


class TestWildcardCharactersAreStorable:
    """`# * !` are wildcards/syntax, not storage errors — writes accept them."""

    @pytest.mark.parametrize("disc_format", FORMATS)
    @pytest.mark.parametrize("name", STORABLE_NAMES)
    def test_write_then_read_back(self, disc_format, name):
        dfs = DFS.create(disc_format)
        payload = b"the quick brown fox"

        dfs.path(f"$.{name}").write_bytes(payload, load_address=0x1900)

        assert dfs.path(f"$.{name}").read_bytes() == payload

    @pytest.mark.parametrize("disc_format", FORMATS)
    @pytest.mark.parametrize("name", STORABLE_NAMES)
    def test_name_appears_in_catalogue(self, disc_format, name):
        dfs = DFS.create(disc_format)
        dfs.path(f"$.{name}").write_bytes(b"x")

        stored = {entry.filename for entry in dfs.files}
        assert name in stored


class TestStorageLayerStillBounded:
    """Bytes the seven-bit name field cannot hold remain hard errors."""

    @pytest.mark.parametrize("disc_format", FORMATS)
    def test_overlength_rejected(self, disc_format):
        dfs = DFS.create(disc_format)
        with pytest.raises(ValueError):
            dfs.path("$.TOOLONGNAME").write_bytes(b"x")

    @pytest.mark.parametrize("disc_format", FORMATS)
    def test_control_character_rejected(self, disc_format):
        dfs = DFS.create(disc_format)
        with pytest.raises(ValueError):
            dfs.path("$.A\x01B").write_bytes(b"x")

    @pytest.mark.parametrize("disc_format", FORMATS)
    def test_top_bit_set_rejected(self, disc_format):
        dfs = DFS.create(disc_format)
        with pytest.raises(ValueError):
            dfs.path("$.A\xffB").write_bytes(b"x")

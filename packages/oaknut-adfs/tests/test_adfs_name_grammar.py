"""ADFS create-time name validation.

oaknut gates *creating* a name by what the ten-byte field can hold and
ADFS can read back — the hard format limits (length, the seven-bit field,
the CR terminator) — not by what the ADFS command parser would accept.
Parser-illegal but representable names (wildcards, directory specials,
spaces) are therefore writable, as on a byte-edited game disc. Reading
and navigation are never gated, so such a disc still lists and reads.
"""

import pytest
from oaknut.adfs import ADFS, ADFS_S
from oaknut.adfs.exceptions import ADFSPathError


class TestHardLimitsRejected:
    """The format's own limits are enforced when creating a name."""

    def test_over_ten_characters_is_an_error_not_truncation(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="too long"):
            (adfs.root / "ELEVENCHARS").write_bytes(b"x")  # 11 chars
        # The over-long name must not have been silently truncated in.
        assert [p.name for p in adfs.root] == []

    def test_top_bit_set_is_rejected(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="top bit set"):
            (adfs.root / "A\xaaB").write_bytes(b"x")

    def test_carriage_return_is_rejected(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="Forbidden character"):
            (adfs.root / "A\rB").write_bytes(b"x")

    def test_colon_is_rejected(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="Forbidden character"):
            (adfs.root / "A:B").write_bytes(b"x")

    def test_mkdir_validates_the_new_directory_name(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError, match="too long"):
            (adfs.root / "ELEVENCHARS").mkdir()

    def test_rename_validates_the_target_name(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "OK").write_bytes(b"x")
        with pytest.raises(ADFSPathError, match="top bit set"):
            (adfs.root / "OK").rename("$.A\xaaB")


class TestParserIllegalNamesAreWritable:
    """Wildcards and specials are representable, so oaknut stores them."""

    @pytest.mark.parametrize("name", ["GAME*", "A#B", "MAP&1", "MY GAME"])
    def test_write_then_read_back(self, name):
        adfs = ADFS.create(ADFS_S)
        payload = b"representable-but-parser-illegal"

        (adfs.root / name).write_bytes(payload)

        assert (adfs.root / name).read_bytes() == payload
        assert name in [p.name for p in adfs.root]

    def test_mkdir_accepts_a_wildcard_name(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "DIR*").mkdir()
        assert (adfs.root / "DIR*").is_dir()


class TestNavigationStaysLiberal:
    """Building or probing a path never validates — only creation does."""

    def test_path_with_forbidden_char_constructs_without_raising(self):
        adfs = ADFS.create(ADFS_S)
        # A handle to a parser-illegal name is a value, not a write.
        handle = adfs.root / "NO:PE"
        assert handle.name == "NO:PE"

    def test_exists_on_forbidden_name_is_false_not_an_error(self):
        adfs = ADFS.create(ADFS_S)
        assert (adfs.root / "A:B").exists() is False

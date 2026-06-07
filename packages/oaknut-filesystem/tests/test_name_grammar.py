"""Tests for NameGrammar — the storable-name rules behind a filesystem's
write validation and its ``describe-filesystem`` reporting."""

import pytest
from oaknut.filesystem import NameGrammar

# A grammar shaped like the DFS one: seven-bit, seven characters, the two
# path separators forbidden, names folded to upper case.
DFS_LIKE = NameGrammar(
    max_length=7,
    forbidden=":.",
    forbidden_reason="the drive (:) and directory (.) separators",
    seven_bit=True,
    case="fold-upper",
    notes=("The wildcard characters * and # are stored literally.",),
)


class TestValidate:
    def test_accepts_a_plain_name(self):
        DFS_LIKE.validate("HELLO")  # no raise

    @pytest.mark.parametrize("name", ["GUARD#1", "SAVE*", "DATA!1", "!BOOT"])
    def test_accepts_wildcard_and_bang_bytes(self, name):
        # The liberal core: metacharacters are storable name bytes.
        DFS_LIKE.validate(name)

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="empty"):
            DFS_LIKE.validate("")

    def test_rejects_overlength(self):
        with pytest.raises(ValueError, match="too long"):
            DFS_LIKE.validate("TOOLONGNAME")

    @pytest.mark.parametrize("name", ["A.B", "A:B"])
    def test_rejects_forbidden_separator(self, name):
        with pytest.raises(ValueError, match="Forbidden character"):
            DFS_LIKE.validate(name)

    def test_rejects_top_bit_set(self):
        with pytest.raises(ValueError, match="top bit set"):
            DFS_LIKE.validate("A\xffB")

    def test_rejects_control_character(self):
        with pytest.raises(ValueError, match="Control character"):
            DFS_LIKE.validate("A\x01B")

    def test_allow_control_permits_low_bytes(self):
        grammar = NameGrammar(max_length=8, allow_control=True)
        grammar.validate("A\x01B")  # no raise

    def test_codec_round_trip_is_enforced(self):
        # A codec that cannot encode the name fails validation.
        grammar = NameGrammar(max_length=8, seven_bit=False, codec="ascii")
        with pytest.raises(ValueError, match="invalid characters"):
            grammar.validate("café")


class TestSummary:
    def test_summary_covers_each_rule(self):
        text = DFS_LIKE.summary()
        assert "up to 7 characters" in text
        assert "Forbidden: : . (the drive (:) and directory (.) separators)" in text
        assert "folded to upper case" in text
        assert "seven-bit" in text
        assert "no control characters" in text
        # Notes are appended verbatim.
        assert "* and # are stored literally" in text

    def test_no_forbidden_reads_cleanly(self):
        text = NameGrammar(max_length=10).summary()
        assert "Forbidden: none" in text

    def test_space_renders_as_a_word(self):
        # A forbidden space would vanish into the join; show it as a word.
        text = NameGrammar(max_length=10, forbidden=":. ").summary()
        assert "Forbidden: : . space" in text

    @pytest.mark.parametrize(
        "case,expected",
        [
            ("fold-upper", "folded to upper case"),
            ("insensitive", "preserved as written, matched case-insensitively"),
            ("sensitive", "case-sensitive"),
        ],
    )
    def test_case_handling_is_described(self, case, expected):
        text = NameGrammar(max_length=8, case=case).summary()
        assert expected in text

    def test_eight_bit_grammar_reads_as_eight_bit(self):
        text = NameGrammar(max_length=10, seven_bit=False, allow_control=True).summary()
        assert "Bytes: eight-bit" in text
        assert "control characters allowed" in text

    def test_control_forbidden_char_renders_by_name(self):
        # A forbidden CR must not put a literal carriage return in the listing.
        text = NameGrammar(max_length=10, forbidden=".\r").summary()
        assert "Forbidden: . CR" in text


class TestNameKey:
    """name_key is the comparator: equal keys mean the same object."""

    def test_fold_upper_collapses_case(self):
        grammar = NameGrammar(max_length=10, case="fold-upper")
        assert grammar.name_key("Hello") == grammar.name_key("HELLO")

    def test_insensitive_collapses_case(self):
        grammar = NameGrammar(max_length=10, case="insensitive")
        assert grammar.name_key("Hello") == grammar.name_key("hello")

    def test_sensitive_distinguishes_case(self):
        grammar = NameGrammar(max_length=10, case="sensitive")
        assert grammar.name_key("Hello") != grammar.name_key("HELLO")
        assert grammar.name_key("Hello") == "Hello"

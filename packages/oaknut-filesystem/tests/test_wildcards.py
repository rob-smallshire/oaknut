"""Tests for the wildcard matchers behind the WildcardMatching capability."""

from oaknut.filesystem import WildcardMatching, WildcardSyntax
from oaknut.filesystem.wildcards import (
    ACORN_MATCHER,
    ACORN_WILDCARDS,
    UNIX_MATCHER,
    UNIX_WILDCARDS,
)


class TestWildcardSyntax:
    def test_chars_and_summary(self):
        assert ACORN_WILDCARDS.chars == "*#"
        assert UNIX_WILDCARDS.chars == "*?"
        assert ACORN_WILDCARDS.summary() == (
            "* (any sequence of characters), # (exactly one character)"
        )


class TestMatchersAreCapabilities:
    def test_both_satisfy_the_protocol(self):
        assert isinstance(ACORN_MATCHER, WildcardMatching)
        assert isinstance(UNIX_MATCHER, WildcardMatching)


class TestAcornMatching:
    def test_star_and_hash(self):
        assert ACORN_MATCHER.matches("FOO*", "FOOBAR")
        assert ACORN_MATCHER.matches("F#O", "FXO")
        assert not ACORN_MATCHER.matches("F#O", "FXYO")  # # is exactly one

    def test_question_mark_is_literal_not_a_wildcard(self):
        # The whole point: ? is an ordinary character on Acorn.
        assert not ACORN_MATCHER.is_pattern("ZALAGA?")
        assert ACORN_MATCHER.matches("ZALAGA?", "ZALAGA?")
        assert not ACORN_MATCHER.matches("ZALAGA?", "ZALAGAB")

    def test_is_pattern_detects_acorn_metachars_only(self):
        assert ACORN_MATCHER.is_pattern("FOO*")
        assert ACORN_MATCHER.is_pattern("FO#O")
        assert not ACORN_MATCHER.is_pattern("PLAINNAME")

    def test_case_insensitive(self):
        assert ACORN_MATCHER.matches("foo*", "FOOBAR")
        assert ACORN_MATCHER.matches("FOO*", "foobar")

    def test_syntax_reported(self):
        assert ACORN_MATCHER.wildcard_syntax is ACORN_WILDCARDS


class TestUnixMatching:
    def test_question_mark_is_a_wildcard(self):
        assert UNIX_MATCHER.is_pattern("FOO?")
        assert UNIX_MATCHER.matches("FOO?", "FOOB")
        assert not UNIX_MATCHER.matches("FOO?", "FOOBB")

    def test_hash_is_literal(self):
        assert not UNIX_MATCHER.is_pattern("FO#")
        assert UNIX_MATCHER.matches("FO#", "FO#")
        assert not UNIX_MATCHER.matches("FO#", "FOX")

    def test_star(self):
        assert UNIX_MATCHER.matches("F*", "FOOBAR")


class TestBracketsAreLiteral:
    def test_square_brackets_never_form_a_set(self):
        # fnmatch char-classes must not leak through: [AB] is a literal name.
        assert ACORN_MATCHER.matches("[AB]", "[AB]")
        assert not ACORN_MATCHER.matches("[AB]", "A")
        assert UNIX_MATCHER.matches("[AB]", "[AB]")
        assert not UNIX_MATCHER.matches("[AB]", "A")


def test_wildcard_syntax_is_exported():
    assert isinstance(ACORN_WILDCARDS, WildcardSyntax)

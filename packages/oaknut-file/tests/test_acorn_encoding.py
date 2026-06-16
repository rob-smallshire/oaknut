"""Tests for Acorn DFS filename helpers.

The character-set codec itself now lives in ``oaknut-codecs`` and is
tested there; this module covers the filename-validity helpers that
remain in :mod:`oaknut.file.acorn_encoding`.
"""

from oaknut.file.acorn_encoding import (
    is_valid_acorn_filename_char,
    sanitize_for_acorn,
)


class TestIsValidAcornFilenameChar:
    """Tests for filename character validation."""

    def test_uppercase_letters(self):
        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            assert is_valid_acorn_filename_char(char)

    def test_digits(self):
        for char in "0123456789":
            assert is_valid_acorn_filename_char(char)

    def test_pound_sign(self):
        assert is_valid_acorn_filename_char("£")

    def test_common_punctuation(self):
        for char in "$%&()+@^_-":
            assert is_valid_acorn_filename_char(char)

    def test_lowercase_invalid(self):
        assert not is_valid_acorn_filename_char("a")
        assert not is_valid_acorn_filename_char("z")

    def test_space_invalid(self):
        assert not is_valid_acorn_filename_char(" ")

    def test_special_chars_invalid(self):
        assert not is_valid_acorn_filename_char("*")
        assert not is_valid_acorn_filename_char("/")
        assert not is_valid_acorn_filename_char("\\")
        assert not is_valid_acorn_filename_char(":")


class TestSanitizeForAcorn:
    """Tests for filename sanitization."""

    def test_converts_to_uppercase(self):
        assert sanitize_for_acorn("hello") == "HELLO"

    def test_removes_invalid_chars(self):
        assert sanitize_for_acorn("HE*LLO") == "HELLO"

    def test_preserves_valid_chars(self):
        assert sanitize_for_acorn("TEST-123") == "TEST-123"

    def test_handles_pound_sign(self):
        assert sanitize_for_acorn("£100") == "£100"

    def test_removes_spaces(self):
        assert sanitize_for_acorn("HELLO WORLD") == "HELLOWORLD"

    def test_mixed_case_and_invalid(self):
        assert sanitize_for_acorn("TeSt*FiLe.BIN") == "TESTFILEBIN"

    def test_empty_string(self):
        assert sanitize_for_acorn("") == ""

    def test_all_invalid_chars(self):
        assert sanitize_for_acorn("***") == ""

    def test_preserves_numbers(self):
        assert sanitize_for_acorn("file123") == "FILE123"

    def test_preserves_punctuation(self):
        assert sanitize_for_acorn("test!@#$%") == "TEST@$%"

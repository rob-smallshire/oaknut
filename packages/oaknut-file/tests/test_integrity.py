"""Tests for the shared no-duplicate-names directory post-condition."""

import pytest
from oaknut.file.integrity import assert_no_duplicate_names, find_duplicate_names


_FOLD_UPPER = str.upper


class TestFindDuplicateNames:
    def test_no_duplicates(self):
        assert find_duplicate_names(["A", "B", "C"]) == []

    def test_exact_match_by_default(self):
        # No key supplied → identity: only exact repeats collide.
        assert find_duplicate_names(["Hello", "HELLO"]) == []

    def test_reports_each_duplicate_once(self):
        assert find_duplicate_names(["A", "B", "A", "B", "A"]) == ["A", "B"]

    def test_key_folds_case_when_supplied(self):
        assert find_duplicate_names(["Hello", "HELLO"], key=_FOLD_UPPER) == ["HELLO"]

    def test_key_can_keep_case_distinct(self):
        # A "sensitive" key (identity) keeps differently-cased names apart.
        assert find_duplicate_names(["Hello", "HELLO"], key=lambda n: n) == []


class TestAssertNoDuplicateNames:
    def test_passes_when_unique(self):
        assert_no_duplicate_names(["A", "B", "C"])

    def test_raises_on_duplicate(self):
        with pytest.raises(AssertionError, match="duplicate entries"):
            assert_no_duplicate_names(["A", "A"])

    def test_message_names_the_location(self):
        with pytest.raises(AssertionError, match=r"\$\.DIR has duplicate entries"):
            assert_no_duplicate_names(["X", "X"], where="$.DIR")

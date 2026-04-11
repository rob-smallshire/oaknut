"""Tests for oaknut.afs.path.AFSPath."""

from __future__ import annotations

import pytest
from oaknut.afs import AFSPathError
from oaknut.afs.path import ROOT, SEPARATOR, AFSPath


class TestRoot:
    def test_root_is_dollar(self) -> None:
        assert str(AFSPath.root()) == ROOT

    def test_root_is_absolute(self) -> None:
        assert AFSPath.root().is_absolute()

    def test_root_is_root(self) -> None:
        assert AFSPath.root().is_root()

    def test_parent_of_root_is_root(self) -> None:
        assert AFSPath.root().parent.is_root()

    def test_name_of_root(self) -> None:
        assert AFSPath.root().name == ROOT


class TestJoin:
    def test_single_component(self) -> None:
        path = AFSPath.root() / "Library"
        assert str(path) == "$.Library"

    def test_two_components(self) -> None:
        path = AFSPath.root() / "Library" / "Fs"
        assert str(path) == "$.Library.Fs"

    def test_three_components(self) -> None:
        path = AFSPath.root() / "BeebMaster" / "Games" / "Elite"
        assert str(path) == "$.BeebMaster.Games.Elite"


class TestName:
    def test_leaf_name(self) -> None:
        assert (AFSPath.root() / "Library" / "Fs").name == "Fs"

    def test_name_of_single_component(self) -> None:
        assert (AFSPath.root() / "Library").name == "Library"


class TestParent:
    def test_parent_of_leaf(self) -> None:
        path = AFSPath.root() / "Library" / "Fs"
        assert str(path.parent) == "$.Library"

    def test_parent_chain_to_root(self) -> None:
        path = AFSPath.root() / "A" / "B" / "C"
        assert str(path.parent.parent.parent) == ROOT


class TestParse:
    def test_parse_root(self) -> None:
        assert AFSPath.parse("$").is_root()

    def test_parse_one_component(self) -> None:
        path = AFSPath.parse("$.Library")
        assert path.parts == ("$", "Library")

    def test_parse_multiple(self) -> None:
        path = AFSPath.parse("$.BeebMaster.Games.Elite")
        assert path.parts == ("$", "BeebMaster", "Games", "Elite")

    def test_parse_round_trip(self) -> None:
        text = "$.Library.Fs"
        assert str(AFSPath.parse(text)) == text

    def test_parse_empty_rejected(self) -> None:
        with pytest.raises(AFSPathError, match="empty"):
            AFSPath.parse("")

    def test_parse_relative_rejected(self) -> None:
        with pytest.raises(AFSPathError, match="must start at root"):
            AFSPath.parse("Library.Fs")


class TestValidation:
    def test_empty_component(self) -> None:
        with pytest.raises(AFSPathError, match="must not be empty"):
            AFSPath.root() / ""

    def test_too_long_component(self) -> None:
        with pytest.raises(AFSPathError, match="exceeds 10"):
            AFSPath.root() / ("X" * 11)

    def test_component_with_dot(self) -> None:
        with pytest.raises(AFSPathError, match="forbidden character"):
            AFSPath.root() / "has.dot"

    def test_component_with_space(self) -> None:
        with pytest.raises(AFSPathError, match="forbidden character"):
            AFSPath.root() / "has space"

    def test_component_with_colon(self) -> None:
        with pytest.raises(AFSPathError, match="forbidden character"):
            AFSPath.root() / "has:colon"

    def test_exactly_10_chars_accepted(self) -> None:
        AFSPath.root() / ("A" * 10)


class TestFspath:
    def test_str_protocol(self) -> None:
        import os

        path = AFSPath.root() / "Library" / "Fs"
        assert os.fspath(path) == "$.Library.Fs"


class TestImmutability:
    def test_frozen(self) -> None:
        path = AFSPath.root() / "Library"
        with pytest.raises(Exception):
            path.parts = ("$",)  # type: ignore[misc]

    def test_join_returns_new_path(self) -> None:
        original = AFSPath.root() / "Library"
        derived = original / "Fs"
        assert str(original) == "$.Library"
        assert str(derived) == "$.Library.Fs"


class TestRepr:
    def test_repr_contains_str(self) -> None:
        path = AFSPath.root() / "Library" / "Fs"
        assert "Library.Fs" in repr(path)


class TestSeparatorConstant:
    def test_separator_is_dot(self) -> None:
        assert SEPARATOR == "."

    def test_root_is_dollar(self) -> None:
        assert ROOT == "$"

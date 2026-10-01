"""Tests for render_error — the cause-chain + notes walker."""

from __future__ import annotations

from oaknut.exception import DataError, InternalError, render_error


def _lines(exc):
    return list(render_error(exc))


class TestLeaf:
    def test_message_is_first_pair(self) -> None:
        line, is_continuation = _lines(DataError("hello"))[0]
        assert line == "hello"
        assert is_continuation is False

    def test_empty_message_uses_class_name(self) -> None:
        # str(exc) is empty when no args are passed; the renderer
        # falls back to the class name so the user sees *something*.
        line, _ = _lines(InternalError())[0]
        assert line == "InternalError"


class TestNotes:
    def test_notes_render_as_continuations(self) -> None:
        exc = DataError("primary")
        exc.add_note("first note")
        exc.add_note("second note")
        lines = _lines(exc)
        assert lines == [
            ("primary", False),
            ("first note", True),
            ("second note", True),
        ]


class TestCauseChain:
    def test_walks_the_cause_chain(self) -> None:
        # Build a chained exception manually so we don't need an
        # actual `raise X from Y` in the test body.
        original = ValueError("root cause")
        intermediate = DataError("intermediate")
        intermediate.__cause__ = original
        leaf = DataError("leaf")
        leaf.__cause__ = intermediate

        lines = _lines(leaf)
        assert lines == [
            ("leaf", False),
            ("caused by: intermediate", True),
            ("caused by: root cause", True),
        ]

    def test_notes_on_cause_chain(self) -> None:
        original = ValueError("root cause")
        original.add_note("a note on the root")
        leaf = DataError("leaf")
        leaf.__cause__ = original

        lines = _lines(leaf)
        assert lines == [
            ("leaf", False),
            ("caused by: root cause", True),
            ("a note on the root", True),
        ]


class TestRepeatedCause:
    """A wrapper re-raising a cause with the same message prints it once (#78)."""

    def test_a_cause_repeating_the_message_is_skipped(self) -> None:
        exc = DataError("Filename too long")
        exc.__cause__ = ValueError("Filename too long")
        assert _lines(exc) == [("Filename too long", False)]

    def test_a_differing_cause_further_down_is_still_shown(self) -> None:
        exc = DataError("cannot write")
        middle = ValueError("cannot write")
        middle.__cause__ = OSError("disc full")
        exc.__cause__ = middle
        assert _lines(exc) == [("cannot write", False), ("caused by: disc full", True)]

    def test_a_differing_cause_is_shown(self) -> None:
        exc = DataError("cannot write")
        exc.__cause__ = ValueError("bad name")
        assert _lines(exc) == [("cannot write", False), ("caused by: bad name", True)]

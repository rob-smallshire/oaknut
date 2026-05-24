"""Tests for the canonical Acorn text I/O helpers.

These helpers own the "business rule" for moving between Python
strings and Acorn-disc text: the encoding is the BBC character set
by default and the on-disc line terminator is ``\r``. The three
filesystem path classes (DFSPath, ADFSPath, AFSPath) delegate to
these helpers so the rule lives in one place.
"""

from oaknut.file import decode_text, encode_text


class TestDecodeText:
    def test_universal_newlines_translate_cr_to_lf(self):
        assert decode_text(b"line1\rline2\r") == "line1\nline2\n"

    def test_universal_newlines_translate_crlf_to_lf(self):
        assert decode_text(b"line1\r\nline2\r\n") == "line1\nline2\n"

    def test_universal_newlines_pass_lf_unchanged(self):
        assert decode_text(b"already\nnative\n") == "already\nnative\n"

    def test_universal_newlines_mixed(self):
        assert decode_text(b"a\rb\r\nc\nd") == "a\nb\nc\nd"

    def test_empty_newline_string_preserves_terminators(self):
        # newline="" disables the translation, matching Python's
        # ``open(..., newline="")`` convention.
        assert decode_text(b"a\rb\r\nc\n", newline="") == "a\rb\r\nc\n"

    def test_acorn_codec_is_default(self):
        # The Acorn character set maps the back-tick position (0x60)
        # to the pound sign.
        assert decode_text(b"\x60") == "£"

    def test_explicit_encoding(self):
        assert decode_text(b"hello", encoding="ascii") == "hello"

    def test_empty(self):
        assert decode_text(b"") == ""


class TestEncodeText:
    def test_default_translates_lf_to_cr(self):
        assert encode_text("line1\nline2\n") == b"line1\rline2\r"

    def test_default_leaves_text_without_lf_alone(self):
        assert encode_text("no newlines") == b"no newlines"

    def test_explicit_crlf_terminator(self):
        assert encode_text("a\nb", newline="\r\n") == b"a\r\nb"

    def test_none_newline_disables_translation(self):
        assert encode_text("a\nb", newline=None) == b"a\nb"

    def test_empty_newline_disables_translation(self):
        assert encode_text("a\nb", newline="") == b"a\nb"

    def test_acorn_codec_is_default(self):
        # The Acorn character set encodes the pound sign at 0x60
        # (the back-tick position).
        assert encode_text("£") == b"\x60"

    def test_explicit_encoding(self):
        assert encode_text("hello", encoding="ascii") == b"hello"

    def test_empty(self):
        assert encode_text("") == b""


class TestRoundTrip:
    def test_python_multiline_round_trips_through_acorn(self):
        # Writing a natural Python multiline string and reading it back
        # with the defaults should give the same Python string.
        source = "alpha\nbeta\ngamma\n"
        assert decode_text(encode_text(source)) == source

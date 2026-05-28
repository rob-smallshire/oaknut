"""Canonical text I/O for Acorn files — encoding and line-ending rules.

This module owns oaknut's domain rule for moving between Python
strings and Acorn-disc text:

  - Acorn files store text in the BBC's character set with the
    Acorn-native ``"\\r"`` line terminator.
  - Host Python strings are Unicode with ``"\\n"`` as the natural
    line terminator.

Both halves of the conversion live here so the three path classes —
``DFSPath``, ``ADFSPath``, ``AFSPath`` — share a single source of
truth.  Their ``read_text`` / ``write_text`` methods are thin
wrappers around :func:`decode_text` / :func:`encode_text`.

The line-ending semantics mirror Python's built-in ``open()`` in
text mode, with one Acorn-appropriate adjustment: the *write* side
defaults to translating ``"\\n"`` to ``"\\r"`` so a natural Python
multiline string lands on the disc with the line terminator the
BBC ROM expects.
"""

from __future__ import annotations


def decode_text(data: bytes, *, encoding: str = "acorn", newline: str | None = None) -> str:
    """Decode ``data`` as text, optionally normalising line endings.

    Args:
        data: Raw bytes to decode.
        encoding: Text encoding. Defaults to ``"acorn"`` — the BBC
            character set, registered as a Python codec by
            :mod:`oaknut.file.acorn_encoding`.
        newline: Line-ending translation policy.

          - ``None`` (the default): universal newlines — ``"\\r\\n"``,
            ``"\\r"`` and ``"\\n"`` all become ``"\\n"`` in the
            returned string.
          - ``""``: pass the decoded text through unchanged.
    """
    text = data.decode(encoding)
    if newline is None:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def encode_text(text: str, *, encoding: str = "acorn", newline: str | None = "\r") -> bytes:
    """Encode ``text`` as bytes, optionally translating line endings.

    Args:
        text: String to encode.
        encoding: Text encoding. Defaults to ``"acorn"`` — the BBC
            character set, registered as a Python codec by
            :mod:`oaknut.file.acorn_encoding`.
        newline: Line-ending translation policy.

          - ``"\\r"`` (the default): every ``"\\n"`` in *text* is
            replaced with ``"\\r"`` before encoding. A natural Python
            multiline string lands on the disc with the Acorn-native
            line terminator.
          - ``""`` or ``None``: pass *text* through unchanged.
          - Any other string: replace each ``"\\n"`` with the given
            sequence before encoding.
    """
    if newline:
        text = text.replace("\n", newline)
    return text.encode(encoding)

"""BBC BASIC tokenisation and detokenisation.

Tokenised BBC BASIC is a compact on-disc representation in which
keywords like ``PRINT`` and ``GOTO`` are replaced with single bytes,
line numbers are packed at the start of each line, and string
literals and ``REM`` comments are stored in the Acorn character
encoding. This module converts between source text and that byte
representation.

BBC BASIC is a language, not a text encoding — tokenised programs
are bytecode, not text. The two functions here therefore work in
``str`` ↔ ``bytes`` pairs and must never be composed with
``DFSPath.read_text`` / ``write_text`` (which would silently mangle
the bytecode). The canonical way to move a BASIC program through a
disc image is ``DFSPath.read_basic`` / ``write_basic``, which wrap
these functions with the correct load-address default.

This module is deliberately self-contained — it imports nothing
from the rest of ``oaknut_dfs`` — so it can later be lifted into a
dedicated ``oaknut-basic`` package without refactoring.
"""

from __future__ import annotations


# Canonical load addresses for BBC BASIC programs on each host.
# Programs saved by *SAVE on a real machine use these by default.
BBC_BASIC_LOAD_ADDRESS = 0x1900
ELECTRON_BASIC_LOAD_ADDRESS = 0x0E00


def tokenise(source: str) -> bytes:
    """Tokenise BBC BASIC source text into its on-disc byte form.

    Args:
        source: BBC BASIC source as a Unicode string.

    Returns:
        Tokenised BASIC program bytes, ready to be written to a disc
        image via ``DFSPath.write_bytes`` or ``ADFSPath.write_bytes``.

    Raises:
        NotImplementedError: The tokeniser has not yet been implemented.
    """
    raise NotImplementedError("BBC BASIC tokenisation is not yet implemented")


def detokenise(data: bytes) -> str:
    """Detokenise a BBC BASIC program into source text.

    Args:
        data: Tokenised BASIC program bytes, as read from a disc image.

    Returns:
        BBC BASIC source as a Unicode string.

    Raises:
        NotImplementedError: The detokeniser has not yet been implemented.
    """
    raise NotImplementedError("BBC BASIC detokenisation is not yet implemented")

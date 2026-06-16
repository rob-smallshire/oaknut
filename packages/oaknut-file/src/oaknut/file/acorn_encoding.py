"""Acorn DFS filename helpers, and registration of the ``"acorn"`` codec.

The ``"acorn"`` character-set *codec* itself now lives in the
dependency-free :mod:`oaknut.codecs` package, so that siblings such as
``oaknut-basic`` can use the encoding without depending on
``oaknut-file``. Importing this module re-exports nothing from there — it
simply imports :mod:`oaknut.codecs` for its registration side effect, so
the long-standing ``import oaknut.file.acorn_encoding`` idiom still
guarantees the codec is registered.

What remains here is genuinely file-domain: the rules for which
characters may appear in an Acorn DFS filename.
"""

from __future__ import annotations

import oaknut.codecs  # noqa: F401 - registers the "acorn" codec as a side effect


def is_valid_acorn_filename_char(char: str) -> bool:
    """Check if a character is valid in an Acorn DFS filename.

    Args:
        char: Single character to check.

    Returns:
        True if the character is valid in filenames.

    Notes:
        Per "Guide to Disc Formats.pdf", forbidden characters are:
        - '#', '*', ':', '.', '!' (except '!' as first character)
        - Top-bit set characters (>127)
        - Control characters (<32)

        This function checks general validity. Position-specific rules
        (like '!' only at position 0) must be checked separately.
    """
    # Standard alphanumeric.
    if "A" <= char <= "Z" or "0" <= char <= "9":
        return True

    # Allowed punctuation (excluding forbidden: # * : . !).
    if char in "$%&()+@^_-":
        return True

    # UK-specific characters.
    if char == "£":
        return True

    return False


def sanitize_for_acorn(text: str) -> str:
    """Sanitize a Unicode string for use as an Acorn DFS filename.

    Args:
        text: String to sanitize.

    Returns:
        Sanitized string with invalid characters removed or replaced.

    Notes:
        - Converts lowercase to uppercase.
        - Removes characters that can't be encoded.
    """
    # Convert to uppercase.
    text = text.upper()

    # Keep only valid characters.
    return "".join(c for c in text if is_valid_acorn_filename_char(c))

"""Internal text utilities for rendering extension descriptions.

These small helpers are used by :mod:`oaknut.extension` to turn an
extension class's docstring into a one-line summary or a tidied block.
They are kept internal (underscore-prefixed module) because they are
not part of the public API.
"""


def _is_blank(line: str) -> bool:
    return not line or line.isspace()


def strip_lines(text: str) -> str:
    """Remove leading and trailing blank lines.

    Args:
        text: The text to process.

    Returns:
        The text with any leading and trailing blank-or-whitespace-only
        lines removed. Interior blank lines are preserved.
    """
    lines = text.splitlines()
    start = 0
    while start < len(lines) and _is_blank(lines[start]):
        start += 1
    end = len(lines)
    while end > start and _is_blank(lines[end - 1]):
        end -= 1
    return "\n".join(lines[start:end])


def normalize_name(name: str) -> str:
    """Normalise an extension lookup name.

    Trims surrounding whitespace only; the name is otherwise matched
    against the registered entry-point key verbatim. Hyphens are
    significant — oaknut's user-facing keys are hyphenated
    (``acorn-dfs``) — so they are preserved, not folded to underscores.
    """
    return name.strip()


def first_line(text: str) -> str:
    """Extract the first non-empty line from *text*.

    Useful for one-line summaries in tables where multi-line text wraps
    awkwardly. Returns the empty string if *text* is empty or all
    whitespace.
    """
    if not text:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""

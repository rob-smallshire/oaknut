"""Parser for the fused ``OUTER_PATH:INNER_PATH`` command argument.

Every command that addresses something inside a disc image accepts a
single positional ``COMPOUND_PATH`` where the host image path and the
optional in-image path are joined by a colon. The colon splits at the
first non-Windows-drive colon; any subsequent colon belongs to the
inner path, so a filing-system dispatch prefix
(``adfs:``/``afs:``/``dfs:``) passes through unchanged for
:func:`oaknut.disc.mount.resolve_mount` to act on.

This module knows nothing about filing systems — it neither identifies
images nor maps extensions to formats. Content-first identification and
partition selection live in :mod:`oaknut.disc.mount`.
"""

from __future__ import annotations

from pathlib import Path

import click


def _split_at_outer_colon(text: str) -> tuple[str, str] | None:
    """Find the outer/inner split point at the first non-Windows colon.

    Returns ``(outer_part, inner_part)`` as raw strings, or ``None``
    if no eligible colon is present.

    Windows drive letters (``X:\\``) at the start of *text* are
    skipped so the drive colon is not treated as a split point.
    """
    if ":" not in text:
        return None

    # Skip a Windows drive letter: single ASCII letter followed by :\ or :/.
    start = 0
    if len(text) >= 3 and text[1] == ":" and text[2] in ("\\", "/") and text[0].isalpha():
        start = 2

    idx = text.find(":", start)
    if idx < 0:
        return None

    return text[:idx], text[idx + 1 :]


def parse_compound_path(compound_path: str) -> tuple[Path, str]:
    """Parse a ``COMPOUND_PATH`` into ``(outer_filepath, inner_path)``.

    A ``COMPOUND_PATH`` is the colon-joined ``OUTER_PATH:INNER_PATH``
    used by every command that addresses something inside a disc image.
    The colon splits at the first non-Windows-drive colon; the
    ``INNER_PATH`` may itself start with a filing-system dispatch prefix
    (``adfs:``/``afs:``/``dfs:``) — that prefix is preserved on the
    returned string so :func:`oaknut.disc.mount.resolve_mount` can act on
    it.

    The outer part must exist as a file. When the spec carries a colon
    and the part to its left does not exist, the error message quotes
    only that part, not the whole string, so the user can see exactly
    what was looked up.

    Examples::

        >>> # Plain outer path — no inner component
        >>> parse_compound_path("hd.dat")               # doctest: +SKIP
        (PosixPath('hd.dat'), '')

        >>> # Fused outer:inner
        >>> parse_compound_path("hd.dat:$.Games")       # doctest: +SKIP
        (PosixPath('hd.dat'), '$.Games')

        >>> # Fused with filing-system prefix on the inner path
        >>> parse_compound_path("hd.dat:afs:$.Library") # doctest: +SKIP
        (PosixPath('hd.dat'), 'afs:$.Library')

    Returns ``(outer_filepath, inner_path)`` — *inner_path* is always a
    string (empty when the user did not supply one).
    """
    split = _split_at_outer_colon(compound_path)
    if split is not None:
        outer_part, inner_part = split
        outer_filepath = Path(outer_part)
        if not outer_filepath.is_file():
            raise click.UsageError(f"image not found: {outer_part}")
        return outer_filepath, inner_part

    # No colon → compound_path is the bare outer path with no inner
    # component. Commands that *require* an inner path validate that
    # downstream.
    outer_filepath = Path(compound_path)
    if not outer_filepath.is_file():
        raise click.UsageError(f"image not found: {compound_path}")
    return outer_filepath, ""

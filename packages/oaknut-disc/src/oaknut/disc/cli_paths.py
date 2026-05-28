"""Parser for the fused ``IMAGE_SPEC:PATH_SPEC`` command argument.

Every command that addresses something inside a disc image accepts a
single positional spec where the host image path and the optional
in-image path are joined by a colon. The colon splits at the first
non-Windows-drive colon; any subsequent colon belongs to the in-image
side, so a filing-system dispatch prefix (``adfs:``/``afs:``/``dfs:``)
passes through unchanged for :func:`oaknut.disc.mount.resolve_mount` to
act on.

This module knows nothing about filing systems — it neither identifies
images nor maps extensions to formats. Content-first identification and
partition selection live in :mod:`oaknut.disc.mount`.
"""

from __future__ import annotations

from pathlib import Path

import click


def _split_at_image_colon(text: str) -> tuple[str, str] | None:
    """Find the image/in-image split point at the first non-Windows colon.

    Returns ``(image_part, in_image_part)`` as raw strings, or ``None``
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


def parse_file_spec(file_spec: str) -> tuple[Path, str]:
    """Parse a ``FILE_SPEC`` into ``(image_filepath, path_spec)``.

    A ``FILE_SPEC`` is the colon-joined compound ``IMAGE_SPEC:PATH_SPEC``
    used by every command that addresses something inside a disc image.
    The colon splits at the first non-Windows-drive colon; the
    ``PATH_SPEC`` may itself start with a filing-system dispatch prefix
    (``adfs:``/``afs:``/``dfs:``) — that prefix is preserved on the
    returned string so :func:`oaknut.disc.mount.resolve_mount` can act on
    it.

    The image part must exist as a file. When the spec carries a colon
    and the part to its left does not exist, the error message quotes
    only that part, not the whole string, so the user can see exactly
    what was looked up.

    Examples::

        >>> # Plain image — no in-image path
        >>> parse_file_spec("hd.dat")               # doctest: +SKIP
        (PosixPath('hd.dat'), '')

        >>> # Fused image:path
        >>> parse_file_spec("hd.dat:$.Games")       # doctest: +SKIP
        (PosixPath('hd.dat'), '$.Games')

        >>> # Fused with filing-system prefix on the in-image path
        >>> parse_file_spec("hd.dat:afs:$.Library") # doctest: +SKIP
        (PosixPath('hd.dat'), 'afs:$.Library')

    Returns ``(image_filepath, in_image_path)`` — *in_image_path* is
    always a string (empty when the user did not supply one).
    """
    split = _split_at_image_colon(file_spec)
    if split is not None:
        image_part, in_image_part = split
        image_filepath = Path(image_part)
        if not image_filepath.is_file():
            raise click.UsageError(f"image not found: {image_part}")
        return image_filepath, in_image_part

    # No colon → file_spec is the bare image path with no in-image
    # component. Commands that *require* an in-image path validate
    # that downstream.
    image_filepath = Path(file_spec)
    if not image_filepath.is_file():
        raise click.UsageError(f"image not found: {file_spec}")
    return image_filepath, ""

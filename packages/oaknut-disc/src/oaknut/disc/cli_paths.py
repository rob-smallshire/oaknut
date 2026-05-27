"""Filing-system prefix parser and Acorn path resolution.

Parses the ``FS:path`` convention used to route commands to the
correct partition on dual-partition disc images. The prefix is
case-insensitive and stripped before the bare path is handed to
the library.

Supported prefixes:

- ``dfs:``  — explicit DFS
- ``adfs:`` — explicit ADFS
- ``afs:``  — AFS tail partition (requires ADFS host image)

When no prefix is present, the filing system is auto-detected from
the image's *content* (via :mod:`oaknut.identify`), falling back to
the file extension when the content is not recognised — so a disc
whose extension is missing or wrong still routes correctly.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

import click

# The recognised disc-image extensions are owned by the filesystem
# packages — each declares which extensions denote its format — so the
# CLI never repeats (and cannot drift from) that knowledge.
from oaknut.adfs import IMAGE_FORMAT_BY_EXTENSION as _ADFS_IMAGE_FORMATS
from oaknut.dfs import IMAGE_FORMAT_BY_EXTENSION as _DFS_IMAGE_FORMATS
from oaknut.identify import identify

_FS_PREFIX_RE = re.compile(r"^(dfs|adfs|afs):", re.IGNORECASE)

# Map the package-declared extensions onto the routing enum.
_DFS_EXTENSIONS = frozenset(_DFS_IMAGE_FORMATS)
_ADFS_EXTENSIONS = frozenset(_ADFS_IMAGE_FORMATS)


class FilingSystem(Enum):
    """Identifies which filing system partition to operate on."""

    DFS = "dfs"
    ADFS = "adfs"
    AFS = "afs"


def parse_prefix(text: str) -> tuple[FilingSystem | None, str]:
    """Split a filing-system prefix from an in-image path.

    Returns ``(filing_system, bare_path)`` where *filing_system* is
    ``None`` when no prefix was given (auto-detect).

    Examples::

        >>> parse_prefix("afs:$.Library")
        (FilingSystem.AFS, '$.Library')
        >>> parse_prefix("$.Games.Elite")
        (None, '$.Games.Elite')
        >>> parse_prefix("ADFS:$")
        (FilingSystem.ADFS, '$')
        >>> parse_prefix("afs:")
        (FilingSystem.AFS, '')
    """
    m = _FS_PREFIX_RE.match(text)
    if m is None:
        return None, text
    fs = FilingSystem(m.group(1).lower())
    bare = text[m.end() :]
    return fs, bare


# Default filing system per identified prober family. AFS is a tail
# partition on an ADFS hard disc, so an AFS identification still routes
# to its ADFS host by default; ``afs:`` selects the AFS partition.
_FAMILY_TO_FILING_SYSTEM = {
    "dfs": FilingSystem.DFS,
    "adfs": FilingSystem.ADFS,
    "afs": FilingSystem.ADFS,
}


def detect_filing_system(image_filepath: Path) -> FilingSystem:
    """Detect the default filing system for an image, content first.

    Identifies the image by its *content* — so a disc whose extension
    is missing or wrong still routes correctly — and falls back to the
    file extension when the content is not recognised (a blank image, or
    a format no prober yet detects, such as new-map ADFS).

    Returns the host filing system: an AFS tail partition routes to its
    ADFS host by default, reachable as AFS only via an explicit ``afs:``
    prefix.

    Raises :class:`click.ClickException` when neither content nor
    extension identifies the image.
    """
    by_content = _detect_filing_system_by_content(image_filepath)
    if by_content is not None:
        return by_content
    return _detect_filing_system_by_extension(image_filepath)


def _detect_filing_system_by_content(image_filepath: Path) -> FilingSystem | None:
    """The best disc filing system from content, or None if unrecognised.

    Walks the ranked identification candidates and returns the first
    that maps to a mountable filing system. Returns ``None`` (deferring
    to extension detection) when nothing is recognised or the path
    cannot be read — the latter keeps the function total for callers
    that probe a path that is not (yet) a real file.
    """
    try:
        candidates = identify(image_filepath)
    except OSError:
        return None
    for candidate in candidates:
        filing_system = _FAMILY_TO_FILING_SYSTEM.get(candidate.family)
        if filing_system is not None:
            return filing_system
    return None


def _detect_filing_system_by_extension(image_filepath: Path) -> FilingSystem:
    """Guess the filing system from the image file extension.

    Returns ``FilingSystem.DFS`` for ``.ssd``/``.dsd`` and
    ``FilingSystem.ADFS`` for ``.adf``/``.adl``/``.dat``.

    Raises :class:`click.ClickException` if the extension is
    unrecognised.
    """
    ext = image_filepath.suffix.lower()
    if ext in _DFS_EXTENSIONS:
        return FilingSystem.DFS
    if ext in _ADFS_EXTENSIONS:
        return FilingSystem.ADFS
    raise click.ClickException(
        f"cannot detect filing system from extension '{ext}'; "
        f"use an explicit prefix (dfs:, adfs:, afs:)"
    )


def validate_prefix_for_image(
    requested: FilingSystem,
    detected: FilingSystem,
) -> None:
    """Check that a user-supplied prefix is compatible with the image format.

    Raises :class:`click.ClickException` on mismatch.
    """
    if requested is FilingSystem.DFS and detected is not FilingSystem.DFS:
        raise click.ClickException(
            f"image is {detected.value.upper()} format; cannot access as DFS"
        )
    if requested is FilingSystem.ADFS and detected is FilingSystem.DFS:
        raise click.ClickException("image is DFS format; cannot access as ADFS")
    if requested is FilingSystem.AFS and detected is FilingSystem.DFS:
        raise click.ClickException(
            "image is DFS format; AFS partitions exist only on ADFS hard discs"
        )
    # adfs: on an ADFS image with AFS — fine, operates on ADFS front partition.
    # afs: on an ADFS image — validated later when .afs_partition is checked.


def resolve_path(
    image_filepath: Path,
    in_image_path: str | None,
) -> tuple[FilingSystem, str]:
    """Resolve the filing system and bare path for a command invocation.

    *in_image_path* may be ``None`` (meaning "root" / "whole disc")
    or a string that optionally carries a filing-system prefix.

    Returns ``(filing_system, bare_path)`` where *bare_path* is the
    path with the prefix stripped (empty string when no path was given
    or only a prefix like ``afs:`` was given).
    """
    if in_image_path is None:
        return detect_filing_system(image_filepath), ""

    requested, bare = parse_prefix(in_image_path)
    detected = detect_filing_system(image_filepath)

    if requested is None:
        return detected, bare

    validate_prefix_for_image(requested, detected)
    return requested, bare


def _split_at_image_colon(text: str) -> tuple[str, str] | None:
    """Find the image/in-image split point at the first non-Windows colon.

    Returns ``(image_part, in_image_part)`` as raw strings, or ``None``
    if no eligible colon is present. Unlike :func:`parse_image_path`,
    this does not check whether ``image_part`` exists on disk — that is
    left to the caller, which usually has a better error message to
    give if the LHS is missing.

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


def parse_image_path(text: str) -> tuple[Path, str] | None:
    """Try to parse ``image:in-image-path`` colon syntax.

    Returns ``(image_filepath, in_image_path)`` if the text contains
    a colon where the portion before it is an existing file. The
    in-image portion may itself carry a filing-system prefix (e.g.
    ``afs:$.Library``).

    Returns ``None`` if the text does not match — no colon, or the
    portion before the colon is not an existing file.

    Windows drive letters (``C:\\...``) are recognised and skipped:
    when the text matches ``X:\\`` at the start (a single letter
    followed by ``:\\``), the first colon is not treated as a split
    point.
    """
    split = _split_at_image_colon(text)
    if split is None:
        return None
    image_part, in_image_part = split
    image_filepath = Path(image_part)
    if not image_filepath.is_file():
        return None
    return image_filepath, in_image_part


def parse_file_spec(file_spec: str) -> tuple[Path, str]:
    """Parse a ``FILE_SPEC`` into ``(image_filepath, path_spec)``.

    A ``FILE_SPEC`` is the colon-joined compound ``IMAGE_SPEC:PATH_SPEC``
    used by every command that addresses something inside a disc image.
    The colon splits at the first non-Windows-drive colon; the
    ``PATH_SPEC`` may itself start with a filing-system dispatch prefix
    (``adfs:``/``afs:``/``dfs:``) — that prefix is preserved on the
    returned string so :func:`resolve_path` can act on it.

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

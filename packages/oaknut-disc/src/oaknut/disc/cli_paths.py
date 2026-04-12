"""Filing-system prefix parser and Acorn path resolution.

Parses the ``FS:path`` convention used to route commands to the
correct partition on dual-partition disc images. The prefix is
case-insensitive and stripped before the bare path is handed to
the library.

Supported prefixes:

- ``dfs:``  — explicit DFS
- ``adfs:`` — explicit ADFS
- ``afs:``  — AFS tail partition (requires ADFS host image)

When no prefix is present, the filing system is auto-detected
from the image format.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

import click

_FS_PREFIX_RE = re.compile(r"^(dfs|adfs|afs):", re.IGNORECASE)

# File extensions strongly associated with DFS images.
_DFS_EXTENSIONS = frozenset({".ssd", ".dsd"})

# File extensions strongly associated with ADFS images (floppy and hard disc).
_ADFS_EXTENSIONS = frozenset({".adf", ".adl", ".dat"})


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
    bare = text[m.end():]
    return fs, bare


def detect_filing_system(image_filepath: Path) -> FilingSystem:
    """Guess the default filing system from image file extension.

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
        raise click.ClickException(
            "image is DFS format; cannot access as ADFS"
        )
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

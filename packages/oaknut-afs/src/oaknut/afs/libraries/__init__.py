"""Shipped AFS library disc images.

Each shipped image is a plain ADFS-L disc containing files to be
emplaced into an AFS partition during initialisation. The images
are named for their target AFS directory:

- ``Library.adl``   — BBC Model B/B+ client libraries + shared Utils
- ``Library1.adl``  — Master 128/Compact client libraries
- ``ArthurLib.adl`` — Archimedes client libraries

At runtime :func:`emplace_library` opens the image (shipped or
user-supplied), creates the target directory on the AFS partition,
and copies every file across using :func:`oaknut.file.copy_file`.
"""

from __future__ import annotations

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from oaknut.adfs import ADFS
    from oaknut.afs.afs import AFS

# Shipped image names (without extension) — the canned library set.
SHIPPED_LIBRARIES: tuple[str, ...] = ("Library", "Library1", "ArthurLib")


def is_shipped(name: str) -> bool:
    """True if *name* matches a shipped library image."""
    return name in SHIPPED_LIBRARIES


def shipped_available(name: str) -> bool:
    """True if the shipped ``.adl`` for *name* is bundled."""
    try:
        return resources.files(__name__).joinpath(f"{name}.adl").is_file()
    except (FileNotFoundError, ModuleNotFoundError):
        return False


@contextmanager
def open_shipped(name: str) -> "Iterator[ADFS]":
    """Yield a read-only ADFS handle on the shipped image *name*."""
    from oaknut.adfs import ADFS

    if not shipped_available(name):
        raise FileNotFoundError(
            f"library image '{name}.adl' is not bundled; "
            f"run scripts/build_library_images.py to produce it"
        )
    with resources.as_file(resources.files(__name__).joinpath(f"{name}.adl")) as path:
        with ADFS.from_file(path) as adfs:
            yield adfs


def emplace_library(
    target_afs: "AFS",
    name: str,
    *,
    conflict: str = "overwrite",
) -> list[str]:
    """Emplace a library onto an AFS partition.

    If *name* matches a shipped library (e.g. ``"Library"``), the
    bundled ``.adl`` is used. If *name* ends with ``.adl``, it is
    treated as a path to a user-supplied ADFS image. In both cases,
    every file in the ADFS root is copied into ``$.{dirname}`` on
    the target AFS partition, where *dirname* is the stem of the
    image filename.

    The target directory is created if it does not already exist.
    """
    from oaknut.adfs import ADFS
    from oaknut.file.copy import copy_file

    if name.lower().endswith(".adl") or name.lower().endswith(".adf"):
        # User-supplied ADFS image path.
        image_filepath = Path(name)
        dirname = image_filepath.stem
        ctx = ADFS.from_file(image_filepath)
    elif is_shipped(name):
        dirname = name
        ctx = open_shipped(name)
    else:
        raise ValueError(
            f"'{name}' is not a shipped library name ({', '.join(SHIPPED_LIBRARIES)}) "
            f"and does not look like an ADFS image path (no .adl/.adf suffix)"
        )

    target_dir = target_afs.root / dirname
    if not target_dir.exists():
        target_dir.mkdir()

    replaced: list[str] = []
    with ctx as adfs:
        for entry in adfs.root.iterdir():
            if entry.stat().is_directory:
                continue
            dest = target_dir / entry.name
            if dest.exists():
                if conflict == "skip":
                    continue
                elif conflict == "overwrite":
                    replaced.append(entry.name)
                    dest.unlink()
                else:
                    from oaknut.afs.exceptions import AFSMergeConflictError

                    raise AFSMergeConflictError(
                        f"'{entry.name}' already exists in $.{dirname}"
                    )
            copy_file(entry, dest, target_fs="afs")
    return replaced

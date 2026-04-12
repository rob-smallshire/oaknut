#!/usr/bin/env python3
"""Build shipped library disc images from econet-fs.tar.

Extracts the four library directories (Library, Library1, ArthurLib,
Utils) from the source tarball and packages each into a standalone
ADFS-L disc image with an initialised AFS partition whose root
contains that library's files. The resulting ``.adl`` files are
written to ``src/oaknut/afs/libraries/`` where
:class:`oaknut.afs.libraries.LibraryImage` discovers them at
runtime via ``importlib.resources``.

Usage::

    python scripts/build_library_images.py /path/to/econet-fs.tar

Or with no arguments, the default source path is::

    /Users/rjs/Code/beebium/discs/l3fs/libraries/econet-fs.tar
"""

from __future__ import annotations

import datetime
import sys
import tarfile
import tempfile
from pathlib import Path

from oaknut.adfs import ADFS, ADFS_L
from oaknut.afs.libraries import LibraryImage

_DEFAULT_TAR = Path("/Users/rjs/Code/beebium/discs/l3fs/libraries/econet-fs.tar")

_LIBRARY_MAP: dict[LibraryImage, str] = {
    LibraryImage.MODEL_B: "Library",
    LibraryImage.MASTER: "Library1",
    LibraryImage.ARCHIMEDES: "ArthurLib",
    LibraryImage.UTILS: "Utils",
}

_DEST_DIRPATH = Path(__file__).resolve().parent.parent / "src" / "oaknut" / "afs" / "libraries"


def build_one(
    library: LibraryImage,
    source_dirpath: Path,
    dest_dirpath: Path,
) -> Path:
    """Build one library ``.adl`` from an extracted host directory.

    The result is a plain ADFS-L image (no AFS partition) with the
    library files stored as regular ADFS files in the root directory.
    """
    dest_filepath = dest_dirpath / library.value
    print(f"  {library.name:15s} ← {source_dirpath} → {dest_filepath.name}")

    adfs = ADFS.create(ADFS_L, title=library.name)

    for host_file in sorted(source_dirpath.iterdir()):
        if host_file.is_file() and not host_file.name.startswith("."):
            target = adfs.root / host_file.name
            target.import_file(host_file)

    disc_bytes = bytes(adfs._disc._disc_image._buffer)
    dest_filepath.write_bytes(disc_bytes)
    return dest_filepath


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    tar_filepath = Path(args[0]) if args else _DEFAULT_TAR
    if not tar_filepath.exists():
        print(f"error: {tar_filepath} not found", file=sys.stderr)
        return 1

    print(f"source: {tar_filepath}")
    print(f"dest:   {_DEST_DIRPATH}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        with tarfile.open(tar_filepath, "r:*") as tf:
            tf.extractall(tmp, filter="data")

        for library, dirname in _LIBRARY_MAP.items():
            source_dirpath = tmp / dirname
            if not source_dirpath.is_dir():
                print(
                    f"  warning: {dirname}/ not found in tarball, skipping",
                    file=sys.stderr,
                )
                continue
            build_one(library, source_dirpath, _DEST_DIRPATH)

    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build shipped library disc images from econet-fs.tar.

Extracts the library directories from the source tarball and packages
each into a standalone plain ADFS-L disc image. The resulting ``.adl``
files are written to ``src/oaknut/afs/libraries/`` where
:func:`emplace_library` discovers them at runtime via
``importlib.resources``.

Each shipped image is named for the AFS directory it will be
emplaced into:

- ``Library.adl``   — BBC Model B/B+ client libraries + shared Utils
- ``Library1.adl``  — Master 128/Compact client libraries
- ``ArthurLib.adl`` — Archimedes client libraries

Usage::

    python scripts/build_library_images.py /path/to/econet-fs.tar

Or with no arguments, the default source path is::

    /Users/rjs/Code/beebium/discs/l3fs/libraries/econet-fs.tar
"""

from __future__ import annotations

import sys
import tarfile
import tempfile
from pathlib import Path

from oaknut.adfs import ADFS, ADFS_L

_DEFAULT_TAR = Path("/Users/rjs/Code/beebium/discs/l3fs/libraries/econet-fs.tar")

# Each output image and the tar directories whose files it contains.
# When multiple source directories map to one image, their files are
# merged (later directories overwrite earlier ones on name collision).
_IMAGE_SPEC: dict[str, list[str]] = {
    "Library": ["Utils", "Library"],
    "Library1": ["Library1"],
    "ArthurLib": ["ArthurLib"],
}

_DEST_DIRPATH = Path(__file__).resolve().parent.parent / "src" / "oaknut" / "afs" / "libraries"


def build_one(
    image_name: str,
    source_dirpaths: list[Path],
    dest_dirpath: Path,
) -> Path:
    """Build one library ``.adl`` from one or more host directories.

    The result is a plain ADFS-L image with the library files stored
    as regular ADFS files in the root directory.
    """
    dest_filepath = dest_dirpath / f"{image_name}.adl"
    print(f"  {image_name + '.adl':20s} ← {', '.join(p.name for p in source_dirpaths)}")

    adfs = ADFS.create(ADFS_L, title=image_name)

    for source_dirpath in source_dirpaths:
        for host_file in sorted(source_dirpath.iterdir()):
            if host_file.is_file() and not host_file.name.startswith("."):
                target = adfs.root / host_file.name
                if target.exists():
                    target.unlink()
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

        for image_name, dirnames in _IMAGE_SPEC.items():
            source_dirpaths = []
            for dirname in dirnames:
                source_dirpath = tmp / dirname
                if not source_dirpath.is_dir():
                    print(
                        f"  warning: {dirname}/ not found in tarball, skipping",
                        file=sys.stderr,
                    )
                    continue
                source_dirpaths.append(source_dirpath)
            if source_dirpaths:
                build_one(image_name, source_dirpaths, _DEST_DIRPATH)

    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

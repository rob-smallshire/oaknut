#!/usr/bin/env python3
"""Build shipped library disc images from econet-fs.tar.

Extracts the four library directories (Library, Library1, ArthurLib,
Utils) from the source tarball and packages each into a standalone
ADFS-L disc image with an initialised AFS partition whose root
contains that library's files. The resulting ``.img`` files are
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
from oaknut.afs.host_import import import_host_tree
from oaknut.afs.libraries import LibraryImage
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise

_DEFAULT_TAR = Path(
    "/Users/rjs/Code/beebium/discs/l3fs/libraries/econet-fs.tar"
)

_LIBRARY_MAP: dict[LibraryImage, str] = {
    LibraryImage.MODEL_B: "Library",
    LibraryImage.MASTER: "Library1",
    LibraryImage.ARCHIMEDES: "ArthurLib",
    LibraryImage.UTILS: "Utils",
}

_DEST_DIRPATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "oaknut"
    / "afs"
    / "libraries"
)


def build_one(
    library: LibraryImage,
    source_dirpath: Path,
    dest_dirpath: Path,
) -> Path:
    """Build one library ``.img`` from an extracted host directory."""
    dest_filepath = dest_dirpath / library.value
    print(f"  {library.name:15s} ← {source_dirpath} → {dest_filepath.name}")

    # Create a blank ADFS-L disc as the host.
    adfs = ADFS.create(ADFS_L)

    # Initialise a generous AFS partition with a single Syst user.
    initialise(
        adfs,
        spec=InitSpec(
            disc_name=library.name,
            date=datetime.date.today(),
            size=AFSSizeSpec.cylinders(150),
            users=[UserSpec("Syst", system=True, quota=0xFFFFFF)],
        ),
    )

    afs = adfs.afs_partition
    assert afs is not None

    # Import the host tree into the AFS root.
    import_host_tree(
        afs,
        source=source_dirpath,
        target_path=afs.root,
        on_collision="overwrite",
    )
    afs.flush()

    # Write the raw disc bytes to the .img file.
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

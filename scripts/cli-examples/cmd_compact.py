"""Example for ``disc compact`` — consolidate free space (ADFS).

Uses the smallest ADFS format (ADFS-S, 640 sectors) so the
``disc freemap`` grids stay compact. The disc is filled almost to
capacity with varied-size files spread across a nested directory
tree, then half of them are deleted, leaving the scattered free
regions that make compaction worth showing. The build is done with
the library API since it is scaffolding the reader is not meant to
see; the ``disc freemap`` / ``disc compact`` transcript is the point.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show  # noqa: E402
from oaknut.adfs import ADFS, ADFS_S  # noqa: E402

# Varied file sizes (in sectors), cycled, so the gaps left by deletion
# differ in size rather than forming a uniform stripe.
_SIZES = [3, 8, 15, 5, 20, 2, 11, 6, 18, 4, 9, 25, 7, 13, 1, 16]
_LOCATIONS = ["", "Games", "Docs", "Src.Lib"]


def _build_fragmented_disc(filepath: str) -> None:
    """Fill an ADFS-S disc nearly full, then delete every other file."""
    with ADFS.create_file(filepath, ADFS_S, title="Demo") as adfs:
        for directory in ("Games", "Docs", "Src"):
            (adfs.root / directory).mkdir()
        (adfs.root / "Src" / "Lib").mkdir()

        created = []
        i = 0
        while True:
            nbytes = _SIZES[i % len(_SIZES)] * 256
            if adfs.free_space < nbytes + 4 * 256:  # leave a little headroom
                break
            target = adfs.root
            for part in _LOCATIONS[i % len(_LOCATIONS)].split("."):
                if part:
                    target = target / part
            target = target / f"F{i:03d}"
            target.write_bytes(b"x" * nbytes, load_address=0x1900, exec_address=0x1900)
            created.append(target)
            i += 1

        # Delete every other file to scatter free space across the disc.
        for index, path in enumerate(created):
            if index % 2 == 0:
                path.unlink()


with in_tmp_dir():
    _build_fragmented_disc("demo.ads")
    show("disc freemap demo.ads")
    show("disc compact demo.ads")
    show("disc freemap demo.ads")

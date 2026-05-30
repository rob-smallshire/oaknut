"""Control storage order to manage seek times.

A floppy (real or emulated) seeks file by file as a game loads, so the
order files lie in on the disc decides how much the head thrashes. This
recipe takes a real game disc, contrives a pathological layout — the big
game file first, the !BOOT file and its loader stranded at the far end —
then uses ``disc compact --order`` to pull the boot files back to the
low sectors where they load fastest, reading the layout before and after
with ``disc storage-order``.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "games" / "Disc001-SnapperV2.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "snapper.ssd")
    # Scaffolding (not shown): drag the big game file to the front and strand
    # !BOOT and the loader at the back — the worst case for seeking. (The
    # game's files are locked; compaction relocates them anyway.)
    silent("disc compact snapper.ssd --order '$.Snappe3,$.SNAPPER,$.Snap2'")

    # The disc as the reader finds it: the 10K game file sits in the lowest
    # sectors, so loading !BOOT means seeking right across the disc first.
    show("disc storage-order snapper.ssd")

    # Pull the boot files to the front, in load order. The rest follow.
    show("disc compact snapper.ssd --order '$.!BOOT,$.SNAP'")

    # !BOOT and its loader now lie first; the bulk data is out of the way.
    show("disc storage-order snapper.ssd")

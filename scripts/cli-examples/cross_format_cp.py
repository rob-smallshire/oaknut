"""Copy files across filing-system formats.

`disc cp` works between any combination of DFS, ADFS, and AFS
images. This recipe pulls two files out of the DFS Repton Infinity
floppy and into a fresh ADFS image, then lists the result so the
reader sees the load / exec / attribute information survived the
crossing.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "games" / "Disc999-ReptonInfinity.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "infinity.ssd")
    silent("disc create stash.adl --format adfs-l --title STASH")

    show("disc cp 'infinity.ssd:$.MENU' 'stash.adl:$.Menu'")
    show("disc cp 'infinity.ssd:$.REPTON' 'stash.adl:$.Repton'")
    show("disc ls stash.adl")

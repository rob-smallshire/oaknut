"""Recipe: build a game cartridge ROM from a DFS game disc.

Copies the BBC Micro game *Snapper* straight off a DFS floppy onto a fresh
paged-ROM cartridge with ``disc cp`` — load and exec addresses carried
across for every file — then gives the cartridge a title and the
publisher's copyright. The whole game fits comfortably in a 16 KiB ROM.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPPER_SSD = REPO_ROOT / "tests" / "data" / "images" / "games" / "Disc001-SnapperV2.ssd"

with in_tmp_dir():
    shutil.copy(SNAPPER_SSD, "snapper.ssd")

    # A fresh 16 KiB cartridge with a title and a *HELP responder, stamped
    # with the publisher's copyright.
    show("disc create SNAPPER.rom --title Snapper")
    show("disc romfs set-copyright SNAPPER.rom '(C) Acornsoft 1982'")

    # Copy the whole game across in one go — disc cp carries each file's
    # load/exec addresses. A bare image path means its root. (cp is silent
    # on success.)
    show("disc cp 'snapper.ssd:$.*' SNAPPER.rom")

    # The finished cartridge.
    show("disc stat SNAPPER.rom")
    show("disc ls SNAPPER.rom")

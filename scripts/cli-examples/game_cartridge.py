"""Recipe: build a game cartridge ROM from an existing game.

Pulls the Zalaga machine-code game out of a reference ROMFS image, then
builds a fresh paged-ROM cartridge for it — a title, the authors'
copyright, and (by default) a ``*HELP`` responder — keeping the game's
load/exec so ``*RUN ZALAGA`` launches it on a real machine.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ZALAGA_ROM = REPO_ROOT / "tests" / "data" / "images" / "romfs" / "Zalaga.rom"

with in_tmp_dir():
    shutil.copy(ZALAGA_ROM, "original.rom")

    # Lift the game's machine code out of the original cartridge.
    silent("disc get original.rom:ZALAGA ZALAGA")

    # Build a fresh 16 KiB cartridge, give it a title, and stamp the
    # authors' copyright (a length change, so the ROM is rebuilt).
    show("disc create ZALAGA.rom --title Zalaga")
    show("disc romfs set-copyright ZALAGA.rom '(C) Nick Pelling & Mike Tomlinson'")

    # Add the game, keeping its load/exec so *RUN ZALAGA launches it.
    show("disc put ZALAGA.rom:ZALAGA ZALAGA --load 0x3000 --exec 0x4522")

    # The finished cartridge.
    show("disc identify ZALAGA.rom")
    show("disc ls ZALAGA.rom")

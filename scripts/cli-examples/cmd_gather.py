"""Example for ``disc gather`` — collate many disc images into one.

Gathers three magazine cover discs (two DFS ``.ssd`` and one ADFS
``.adl``) onto a single ADFS hard-disc image, each under its own
directory named from the source filename.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MAGAZINES = REPO_ROOT / "tests" / "data" / "images" / "magazines"
SOURCES = [
    MAGAZINES / "micro-user" / "D-MU05_01.ssd",
    MAGAZINES / "a-and-b" / "aab-01.ssd",
    MAGAZINES / "acorn-user" / "Tau85-a.adl",
]

with in_tmp_dir():
    silent("mkdir discs")
    for source in SOURCES:
        shutil.copy(source, "discs")

    silent("disc create archive.dat --geometry capacity=5MB --title Mags")
    show("disc gather archive.dat discs/D-MU05_01.ssd discs/aab-01.ssd discs/Tau85-a.adl")
    show("disc tree archive.dat")

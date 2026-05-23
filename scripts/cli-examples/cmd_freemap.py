"""Example for ``disc freemap`` — ASCII fragmentation bar.

Uses a corpus DFS image with a small handful of files so the bar
shows both used (``#``) and free (``.``) sectors.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "games" / "Disc001-PlanetoidAKADefender.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "planet.ssd")
    show("disc freemap planet.ssd")

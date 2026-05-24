"""Repton Infinity: a populated real-world Acorn disc.

Demonstrates that the same `disc` commands the reader just learned
on a synthetic GETSTARTED disc work unchanged on a real Acorn-era
image. The source image lives in the project's test fixtures
(``tests/data/images/games/Disc999-ReptonInfinity.ssd``); we copy
it into a temp working dir before listing so the recipe is
side-effect-free.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "games" / "Disc999-ReptonInfinity.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "infinity.ssd")
    show("disc stat infinity.ssd")
    show("disc ls 'infinity.ssd:$'")
    show("disc type 'infinity.ssd:$.!BOOT'")

"""First contact with a real Acorn disc: Planetoid.

The "First contact" section of the CLI getting-started page uses
Acornsoft's Planetoid (1982) — a small BBC Micro arcade port of
Defender — as the first-real-disc demonstration. The source lives
in the project's test fixtures
(``tests/data/images/games/Disc001-PlanetoidAKADefender.ssd``);
we copy it into a temp working dir before listing so the recipe is
side-effect-free.
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
    shutil.copy(SOURCE, "planetoid.ssd")
    show("disc ls planetoid.ssd")
    show("disc ls 'planetoid.ssd:$'")
    show("disc tree planetoid.ssd")
    show("disc type 'planetoid.ssd:$.!BOOT'")

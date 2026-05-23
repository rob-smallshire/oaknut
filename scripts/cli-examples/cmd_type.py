"""Example for ``disc type`` — show a text file with line-ending translation.

Companion of ``disc cat``. The Acorn-native ``\\r`` line endings are
converted to the host platform's convention so the boot script
displays as separate lines rather than running together.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "games" / "Disc002-Arcadians.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "arcadians.ssd")
    show("disc type 'arcadians.ssd:$.!BOOT'")

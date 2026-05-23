"""Finding files by Acorn wildcard pattern.

Demonstrates `disc find` against a real disc with a mix of files
following different naming conventions — Repton Infinity's editor
suite all ends in `Edit`, and the BBC Master ROM images all start
with `MDROM`.
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
    show("disc find 'infinity.ssd:*Edit'")
    show("disc find 'infinity.ssd:MDROM*'")

"""Example for ``disc get-exec`` — read a file's exec address."""

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
    show("disc get-exec 'arcadians.ssd:$.ARC'")

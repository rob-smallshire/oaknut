"""Example for ``disc export`` — bulk-extract an image to a host tree."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "games" / "Disc002-Arcadians.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "arcadians.ssd")
    silent("mkdir out")
    show("disc export arcadians.ssd out")
    show("ls -C 'out/$'")

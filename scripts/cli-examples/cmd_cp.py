"""Example for ``disc cp`` — copy a file across images and formats."""

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
    silent("disc create archive.adl --title Archive")
    show("disc cp 'arcadians.ssd:$.!BOOT' 'archive.adl:$.!BOOT'")
    show("disc ls archive.adl")

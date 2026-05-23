"""Example for ``disc get`` — export one file from an image.

The command writes the file and a metadata sidecar to the current
directory. Silent on success — a follow-up ``ls`` shows what landed.
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
    show("disc get 'arcadians.ssd:$.!BOOT'")
    show("ls !BOOT*")

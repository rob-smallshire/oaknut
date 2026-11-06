"""Example for ``disc hfe flatten`` — write an HFE capture out as a sector image."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import REPO_ROOT, in_tmp_dir, show  # noqa: E402

HFE_FILEPATH = REPO_ROOT / "tests/data/images/hfe/Dunjunz_D1S2_40T_HG3_54F4B47A_1.hfe"

with in_tmp_dir():
    shutil.copy2(HFE_FILEPATH, "dunjunz-side2.hfe")
    show("disc hfe flatten dunjunz-side2.hfe dunjunz-side2.ssd")
    show("disc stat dunjunz-side2.ssd")

"""Example for ``disc hfe sectors`` — the per-track, per-sector report."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import REPO_ROOT, in_tmp_dir, show  # noqa: E402

HFE_FILEPATH = REPO_ROOT / "tests/data/images/hfe/Dunjunz_D1S1_40T_HG3_8518BF40_1.hfe"

with in_tmp_dir():
    shutil.copy2(HFE_FILEPATH, "dunjunz.hfe")
    show("disc hfe sectors --track 1 --report sectors dunjunz.hfe")
    show("disc hfe sectors --anomalies --report tracks dunjunz.hfe")

"""Example for ``disc storage-order`` — files in physical lay-down order.

The catalogue lists a real DFS disc highest-sector-first, so ``storage-order``
is the way to see the order the files actually lie in — the order they load
in, and the order a faithful copy preserves.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "games" / "Disc001-SnapperV2.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "snapper.ssd")
    show("disc storage-order snapper.ssd")

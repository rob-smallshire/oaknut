"""Example for ``disc identify`` — recognise a disc image by its content.

Run against a Level 3 File Server image, which carries an ADFS host
partition with an AFS tail. Identification reads the bytes rather than
trusting the extension, so it reports both partitions, best guess
first, with the evidence behind each.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "l3fs" / "l3fs-wfsinit.dat"

with in_tmp_dir():
    shutil.copy(SOURCE, "server.dat")
    show("disc identify server.dat")

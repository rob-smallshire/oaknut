"""Example for ``disc import`` — bulk-import a host directory into an image."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.adl --title Demo")
    silent("mkdir host-tree")
    silent("printf 'First document.\\r' > host-tree/DOC1")
    silent("printf 'Second document.\\r' > host-tree/DOC2")
    show("disc import demo.adl host-tree")
    show("disc ls demo.adl")

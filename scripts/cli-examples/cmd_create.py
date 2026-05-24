"""Example for ``disc create`` — create a new empty disc image."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show  # noqa: E402

with in_tmp_dir():
    show("disc create demo.ssd --title Demo")
    show("disc stat demo.ssd")

"""Example for ``disc mkdir`` — create a directory (ADFS-only)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.adl --title Demo")
    show("disc mkdir 'demo.adl:$.Docs' --title 'My Documents'")
    show("disc ls 'demo.adl:$'")
    show("disc title 'demo.adl:$.Docs'")

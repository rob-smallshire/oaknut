"""Example for ``disc title`` — read or set the disc title."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.ssd --title OldName")
    show("disc title demo.ssd")
    show("disc title demo.ssd NewName")
    show("disc title demo.ssd")

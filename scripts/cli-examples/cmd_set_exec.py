"""Example for ``disc set-exec`` — write a file's exec address."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.ssd --format ssd --title Demo")
    silent("printf 'data\\r' | disc put 'demo.ssd:$.FILE' -")
    show("disc set-exec 'demo.ssd:$.FILE' 0x8023")
    show("disc get-exec 'demo.ssd:$.FILE'")

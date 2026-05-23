"""Example for ``disc put`` — import one host file into an image."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.ssd --format ssd --title Demo")
    silent("printf 'Hello from the host.\\r' > greeting.txt")
    show("disc put 'demo.ssd:$.GREET' greeting.txt")
    show("disc ls demo.ssd")

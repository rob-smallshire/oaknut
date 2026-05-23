"""Example for ``disc expand`` — pad a truncated image up to its format size.

Truncated SSDs commonly arise from BeebAsm output, which omits trailing
empty sectors. The recipe simulates this by truncating a freshly-created
image to 1 KB, then runs ``disc expand`` to restore the canonical size.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.ssd --format ssd --title Demo")
    silent("python -c \"import pathlib; open('demo.ssd', 'r+b').truncate(1024)\"")
    show("wc -c < demo.ssd")
    show("disc expand demo.ssd")
    show("wc -c < demo.ssd")

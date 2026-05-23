"""Blank-disc snapshot: create a fresh DFS image and inspect it.

Renders the ``disc stat`` block in the "Build a blank disc to follow
along" section of ``docs/manual/cli/getting-started.rst``. The disc
is empty at this point — the reader has not yet put any files in.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show  # noqa: E402

with in_tmp_dir():
    show("disc create hello.ssd --format ssd --title GETSTARTED")
    show("disc stat hello.ssd")

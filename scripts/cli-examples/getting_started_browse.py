"""Populated-disc snapshot: catalogue listings after a file has been added.

Renders the ``disc tree`` / ``disc ls`` blocks in the "Browsing the
catalogue" section of ``docs/manual/cli/getting-started.rst``. Builds
the same ``hello.ssd`` as the surrounding narrative describes and
writes a short plain-text README into ``$.README`` before listing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create hello.ssd --format ssd --title GETSTARTED")
    silent("printf 'Welcome to the GETSTARTED disc.\\r' > readme.txt")
    silent("disc put 'hello.ssd:$.README' readme.txt")

    show("disc tree hello.ssd")
    show("disc ls 'hello.ssd:$'")

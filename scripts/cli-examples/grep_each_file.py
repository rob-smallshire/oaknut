"""Cookbook recipe: find files on a disc whose contents match a string.

Two stages, each its own ``section()``:

- ``count``  — ``grep -c`` produces a TSV of (path, match-count) for
                every file in the image.
- ``paths``  — the same stream filtered with ``awk`` so only the paths
                of files that actually matched come through.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create code.ssd --title Code")
    silent("printf '10 PROCmenu\\r' | disc put 'code.ssd:$.MAIN' -")
    silent("printf '100 PROCdraw\\r' | disc put 'code.ssd:$.MENU' -")
    silent("printf '10 PRINT \"Hi!\"\\r' | disc put 'code.ssd:$.HELLO' -")
    silent("printf 'a stray data file\\r' | disc put 'code.ssd:$.DATA' -")

    section("count")
    show("disc for-each 'code.ssd:*' -- grep -c PROC")

    section("paths")
    show("disc for-each 'code.ssd:*' -- grep -c PROC | awk -F'\\t' '($2+0) > 0 { print $1 }'")

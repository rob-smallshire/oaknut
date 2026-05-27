"""Example for ``disc title`` — read or set a disc or directory title.

Two cases: the disc-level title (works on every filesystem) and a
per-directory title (ADFS only — DFS and AFS directories have no
title field). Passing a directory path on DFS or AFS is an error.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    # Disc-level title — every filesystem has one.
    silent("disc create demo.ssd --title OldName")
    show("disc title demo.ssd")
    show("disc title demo.ssd NewName")
    show("disc title demo.ssd")

    # Per-directory title — ADFS only.
    silent("disc create games.adl --title Games")
    silent("disc mkdir 'games.adl:$.Elite'")
    show("disc title 'games.adl:$.Elite' Frontier")
    show("disc title 'games.adl:$.Elite'")

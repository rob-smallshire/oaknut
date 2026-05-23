"""Bulk-export a disc to a host directory tree.

Demonstrates `disc export` with INF sidecar metadata. The recipe
extracts Repton Infinity into a host directory and then inspects
the resulting files — the disc's file bytes land alongside ``.inf``
sidecars that capture load / exec / length / attribute information
that does not survive a plain host file system.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "games" / "Disc999-ReptonInfinity.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "infinity.ssd")

    silent("mkdir extracted")
    show("disc export infinity.ssd extracted")

    # The disc's `$` directory becomes `extracted/$/` on host. List
    # the contents so the reader sees the file/sidecar pairing
    # across the whole catalogue.
    show("ls 'extracted/$'")

    # And one sidecar so the on-disc metadata format is visible.
    show("cat 'extracted/$/LOAD.inf'")

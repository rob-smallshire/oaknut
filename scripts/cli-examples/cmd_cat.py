"""Example for ``disc cat`` — write raw file bytes to stdout.

Like Unix ``cat``: no transformation, no line-ending translation —
the bytes on disc are the bytes you get. Piping through ``xxd``
makes the rawness visible: the Acorn ``\\r`` (``0d``) line
terminators are right there in the dump. For terminal-friendly text
display with ``\\r``→``\\n`` conversion, use ``disc type`` instead.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "games" / "Disc002-Arcadians.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "arcadians.ssd")
    show("disc cat 'arcadians.ssd:$.!BOOT' | xxd")

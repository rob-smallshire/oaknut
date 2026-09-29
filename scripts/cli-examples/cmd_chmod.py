"""Example for ``disc chmod`` — set access bits on a file."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.adl --title Demo")
    silent("printf 'A note.\\r' | disc put 'demo.adl:$.File' -")
    silent("printf 'game' | disc put 'demo.adl:$.EliteA' -")
    silent("printf 'game' | disc put 'demo.adl:$.EliteB' -")
    show("disc chmod 'demo.adl:$.File' LWR/R")
    show("disc chmod --dry-run 'demo.adl:$.Elite*' R/R")
    show("disc '*ACCESS' 'demo.adl:$.Elite*' R/R")
    show("disc ls demo.adl")

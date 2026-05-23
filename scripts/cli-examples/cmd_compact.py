"""Example for ``disc compact`` — consolidate free space (ADFS)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.adl --format adfs-m --title Demo")
    silent("printf 'A.\\r' | disc put 'demo.adl:$.First' -")
    silent("printf 'B.\\r' | disc put 'demo.adl:$.Second' -")
    silent("disc rm 'demo.adl:$.First'")
    show("disc freemap demo.adl")
    show("disc compact demo.adl")
    show("disc freemap demo.adl")

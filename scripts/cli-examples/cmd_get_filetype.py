"""Example for ``disc get-filetype`` — read a file's RISC OS filetype."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.adl --title Demo")
    silent("printf 'data\\r' | disc put 'demo.adl:$.FILE' -")
    silent("disc set-filetype 'demo.adl:$.FILE' Obey")
    show("disc get-filetype --as display 'demo.adl:$.FILE'")

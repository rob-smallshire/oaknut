"""Example for ``disc mv`` — rename or move within an image."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.adl --title Demo")
    silent("printf 'A note.\\r' | disc put 'demo.adl:$.Notes' -")
    show("disc mv 'demo.adl:$.Notes' 'demo.adl:$.Memo'")
    show("disc ls demo.adl")

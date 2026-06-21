"""Example for ``disc set-datestamp`` — set a file's datestamp."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.adl --title Demo")
    silent("printf 'data\\r' | disc put 'demo.adl:$.FILE' -")
    show("disc set-datestamp 'demo.adl:$.FILE' 2024-03-01T14:22:08")
    show("disc get-datestamp --as display 'demo.adl:$.FILE'")

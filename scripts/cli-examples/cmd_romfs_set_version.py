"""Example for ``disc romfs set-version`` — set a ROM's binary version byte."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.rom --filesystem acorn-romfs --title DEMO")
    show("disc romfs set-version demo.rom 2")
    show("disc romfs get-version demo.rom")

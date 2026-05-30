"""Example for ``disc romfs set-copyright`` — set a ROM's copyright string.

A length change rebuilds the ROM (regenerating its service handler), done
only for a created-style ROM with no language entry and nothing after the
filing system.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.rom --filesystem acorn-romfs --title DEMO")
    show("disc romfs set-copyright demo.rom '(C) 1984 Acornsoft'")
    show("disc romfs get-copyright demo.rom")

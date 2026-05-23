"""Example for ``disc tree`` — walk a disc as a hierarchical tree.

Builds a small ADFS image with two subdirectories and a couple of
files so the rendered tree exercises both directory and leaf nodes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.adl --format adfs-m --title Demo")
    silent("disc mkdir 'demo.adl:$.Docs'")
    silent("disc mkdir 'demo.adl:$.Code'")
    silent("printf 'Hello from the demo disc.\\r' | disc put 'demo.adl:$.Docs.README' -")
    silent("printf '10 PRINT \"HI\"\\r20 END\\r' | disc put 'demo.adl:$.Code.Hello' -")
    show("disc tree demo.adl")

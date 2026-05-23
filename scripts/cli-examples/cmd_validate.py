"""Example for ``disc validate`` — image-structure consistency check.

Uses a freshly-created ADFS image so the happy-path "OK" verdict is
deterministic. ``disc validate`` exits non-zero if any structural
inconsistency is detected, making it useful in CI pipelines.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.adl --format adfs-m --title Demo")
    show("disc validate demo.adl")

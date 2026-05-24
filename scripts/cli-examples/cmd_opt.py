"""Examples for ``disc opt`` — read and set the boot option.

Multi-section recipe so the auto-generated reference can show each
distinct use case alongside the relevant prose.

Sections:

  read           Read the current boot option (no value supplied).
  set_numeric    Set numerically (0-3).
  set_symbolic   Set symbolically (OFF / LOAD / RUN / EXEC).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create boot.ssd --title BOOTDEMO")

    section("read")
    show("disc opt boot.ssd")

    section("set_numeric")
    show("disc opt boot.ssd 2")
    show("disc opt boot.ssd")

    section("set_symbolic")
    show("disc opt boot.ssd EXEC")
    show("disc opt boot.ssd")

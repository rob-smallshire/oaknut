"""Example for ``disc list-report-formats`` — list output formatters."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import show  # noqa: E402

show("disc list-report-formats")

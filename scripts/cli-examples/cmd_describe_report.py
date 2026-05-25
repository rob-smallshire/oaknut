"""Example for ``disc describe-report`` — describe one declared report."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import show  # noqa: E402

show("disc describe-report ls entries")

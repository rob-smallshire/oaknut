"""Example for ``disc describe-filesystem`` — explain one filesystem.

Prints the full description of a single recognised filesystem,
including how it is told apart from look-alikes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import show  # noqa: E402

show("disc describe-filesystem adfs")

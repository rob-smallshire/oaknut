"""Example for ``disc list-formats`` — the disc formats identification knows.

Each row is a registered prober: the formats ``disc identify`` can
recognise by content. The set grows automatically as format packages
are installed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import show  # noqa: E402

show("disc list-formats")

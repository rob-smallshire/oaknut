"""Example for ``disc list-filesystems`` — the filesystems this build knows.

Each row is a registered filesystem: those ``disc identify`` can
recognise by content and ``--filesystem`` can name. The set grows
automatically as filesystem packages are installed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import show  # noqa: E402

show("disc list-filesystems")

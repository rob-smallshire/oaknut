"""Example for ``disc afs-merge`` — merge a source AFS tree into a target image."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create source.dat --geometry capacity=5MB --title Source")
    silent("disc afs-init source.dat --disc-name Source --emplace Library")
    silent("disc create target.dat --geometry capacity=10MB --title Target")
    silent("disc afs-init target.dat --disc-name Target")
    show("disc afs-merge target.dat --source source.dat")
    show("disc tree target.dat")

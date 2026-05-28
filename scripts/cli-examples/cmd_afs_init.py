"""Example for ``disc afs init`` — carve out an AFS partition."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create scsi0.dat --geometry capacity=10MB --title Server")
    show("disc afs init scsi0.dat --disc-name Server")
    show("disc stat scsi0.dat")

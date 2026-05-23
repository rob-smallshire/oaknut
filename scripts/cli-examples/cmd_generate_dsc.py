"""Example for ``disc generate-dsc`` — synthesise a .dsc geometry sidecar.

Demonstrated against an ADFS hard-disc ``.dat`` image that has no
existing ``.dsc`` next to it — the command writes a 22-byte geometry
record so subsequent ``disc`` commands can open the image.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create scsi0.dat --format adfs-hard --capacity 10MB --title Server")
    silent("rm scsi0.dsc")
    show("disc generate-dsc scsi0.dat --heads 4 --sectors-per-track 33")
    show("ls scsi0.*")

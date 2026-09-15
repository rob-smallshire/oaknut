"""Example for ``disc adfs generate-cfg`` — synthesise a BeebSCSI/Pi1MHz .cfg.

Demonstrated against an ADFS hard-disc ``.dat`` image that has no
existing ``.cfg`` next to it — the command writes a BeebSCSI extended
attributes file whose SCSI mode pages record the disc geometry
(sectors-per-track included), ready to drop onto a Pi1MHz SD card.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create scsi0.dat --geometry capacity=10MB --title Server")
    show("disc adfs generate-cfg scsi0.dat")
    show("ls scsi0.*")

"""Build a bootable Level 3 File Server hard disc image end-to-end.

Six steps:

  1. Create a 10 MiB ADFS hard disc envelope.
  2. Copy the file-server executable in from its DFS floppy.
  3. Write a !BOOT script that *RUNs the file server.
  4. Read the current boot option (OFF on a fresh disc) and set it
     to EXEC so SHIFT-BREAK runs !BOOT.
  5. Plan the AFS partition (afs-plan suggests the cylinders value).
  6. Initialise AFS with users and the shipped library images.

Closes with `disc stat` to confirm the resulting dual-partition
shape. The source SSD with the FS executable lives in the cookbook
corpus at tests/data/images/cookbook/FS3v126.ssd.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "cookbook" / "FS3v126.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "FS3v126.ssd")

    show("disc create scsi0.dat --format adfs-hard --capacity 10MB --title Server")
    show("disc cp 'FS3v126.ssd:$.FS3v126' 'scsi0.dat:$.FS3v126'")

    # Quote the !BOOT body once via printf so the literal CR is
    # preserved across the pipe into disc put.
    silent("printf '*RUN $.FS3v126\\r' > boot.tmp")
    show("disc put 'scsi0.dat:$.!BOOT' boot.tmp")

    show("disc opt scsi0.dat")
    show("disc opt scsi0.dat EXEC")

    show("disc afs-plan scsi0.dat")
    show(
        "disc afs-init scsi0.dat --disc-name Server"
        " --user RJS:2MB"
        " --omit-user Welcome"
        " --emplace Library --emplace Library1"
    )

    show("disc afs-users scsi0.dat")
    show("disc stat scsi0.dat")

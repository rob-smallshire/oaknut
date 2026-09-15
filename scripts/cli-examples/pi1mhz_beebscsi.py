"""Build a Pi1MHz / BeebSCSI hard disc from a shelf of magazine cover discs.

The end-to-end answer to "consolidate my cover-disc collection onto one
virtual hard drive for a real BBC Micro": create an ADFS hard-disc image
with the BeebSCSI geometry sidecars, ``disc gather`` a mix of DFS and
ADFS cover discs onto it (one directory each), and lay the result out
under the SD-card directory the firmware reads.

Sections:

  create   ``disc create`` with ``--sidecar dsc --sidecar cfg`` — the
           empty ADFS LUN image plus both geometry sidecars.
  gather   ``disc gather`` — copy every cover disc into its own
           directory in one command.
  inspect  the gathered directories, and the geometry read back from
           the ``.cfg`` sidecar.
  deploy   drop the image and its sidecars into ``BeebSCSI0/`` on the
           SD card, under the ``scsiN`` LUN names the firmware reads.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MAGAZINES = REPO_ROOT / "tests" / "data" / "images" / "magazines"
SOURCES = [
    MAGAZINES / "micro-user" / "D-MU05_01.ssd",
    MAGAZINES / "micro-user" / "D-MU05_02.ssd",
    MAGAZINES / "a-and-b" / "aab-01.ssd",
    MAGAZINES / "acorn-user" / "Tau85-a.adl",
]

with in_tmp_dir():
    silent("mkdir discs")
    for source in SOURCES:
        shutil.copy(source, "discs")

    section("create")
    # The LUN image is named scsiN.dat from the outset, so its sidecars
    # come out as scsi0.dsc / scsi0.cfg — exactly the names BeebSCSI reads.
    show(
        "disc create scsi0.dat --geometry capacity=20MB "
        "--sidecar dsc --sidecar cfg --title CoverDisc"
    )
    show("ls scsi0.*")

    section("gather")
    show("disc gather scsi0.dat discs/*.ssd discs/*.adl")

    section("inspect")
    show("disc ls 'scsi0.dat:$'")
    show("disc stat scsi0.dat")

    section("deploy")
    show("mkdir -p SDCARD/BeebSCSI0\ncp scsi0.dat scsi0.dsc scsi0.cfg SDCARD/BeebSCSI0/")
    show("ls SDCARD/BeebSCSI0")

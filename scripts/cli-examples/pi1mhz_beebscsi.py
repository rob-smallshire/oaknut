"""Build a Pi1MHz / BeebSCSI hard disc from a shelf of magazine cover discs.

The end-to-end answer to "consolidate my cover-disc collection onto one
virtual hard drive for a real BBC Micro": create an ADFS hard-disc image
with the BeebSCSI geometry sidecar, ``disc gather`` a mix of DFS and ADFS
cover discs onto it (one directory each), and lay the result out under
the SD-card directory the firmware reads.

Sections:

  create   ``disc create`` with ``--sidecar cfg`` — the empty ADFS LUN
           image plus its geometry sidecar.
  gather   ``disc gather`` — copy every cover disc into its own
           directory in one command.
  tree     ``disc tree --depth 1`` — the collection, one directory per
           source disc.
  deploy   drop the image and its sidecar into ``BeebSCSI0/`` on the SD
           card, under the ``scsiN`` LUN name the firmware reads.
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
    # The LUN image is named scsi0.dat from the outset, so its sidecar
    # comes out as scsi0.cfg — exactly the name BeebSCSI reads for LUN 0.
    show("disc create scsi0.dat --geometry capacity=20MB --sidecar cfg --title CoverDisc")

    section("gather")
    show("disc gather scsi0.dat discs/*.ssd discs/*.adl")

    section("tree")
    show("disc tree scsi0.dat --depth 1")

    section("deploy")
    show("mkdir -p SDCARD/BeebSCSI0\ncp scsi0.dat scsi0.cfg SDCARD/BeebSCSI0/")
    show("ls SDCARD/BeebSCSI0")

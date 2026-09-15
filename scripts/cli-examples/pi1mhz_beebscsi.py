"""Prepare a consolidated ADFS hard disc for Pi1MHz / BeebSCSI.

Pi1MHz's BeebSCSI hard-disc emulation serves each virtual drive (LUN)
from an SD card as ``BeebSCSI<n>/scsiN.dat`` — a raw ADFS FileCore image
— beside a geometry sidecar. This recipe builds such an image with both
the binary ``.dsc`` and the richer BeebSCSI ``.cfg`` sidecars, copies a
shelf of dated cover discs into per-issue directories, and lays the
result out under the SD-card directory the firmware expects.

Sections:

  create   ``disc create`` with ``--sidecar dsc --sidecar cfg`` — the
           empty ADFS hard-disc image plus both geometry sidecars.
  import   the ``for`` loop that copies each cover disc into its own
           directory (see the SSD-archive recipe for the mechanics).
  stat     the geometry read back from the ``.cfg`` sidecar.
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
TELEMETRY_DIR = REPO_ROOT / "tests" / "data" / "images" / "telemetry"
ISSUES = {"8402": "telem-8402.ssd", "8404": "telem-8404.ssd"}

with in_tmp_dir():
    silent("mkdir discs")
    for issue, filename in ISSUES.items():
        shutil.copy(TELEMETRY_DIR / filename, f"discs/{issue}.ssd")

    section("create")
    # The LUN image is named scsiN.dat from the outset, so its sidecars
    # come out as scsi0.dsc / scsi0.cfg — exactly the names BeebSCSI reads.
    show(
        "disc create scsi0.dat --geometry capacity=20MB "
        "--sidecar dsc --sidecar cfg --title CoverDisc"
    )
    show("ls scsi0.*")

    section("import")
    show("disc gather scsi0.dat discs/*.ssd")

    section("stat")
    show("disc stat scsi0.dat")

    section("deploy")
    show("mkdir -p SDCARD/BeebSCSI0\ncp scsi0.dat scsi0.dsc scsi0.cfg SDCARD/BeebSCSI0/")
    show("ls SDCARD/BeebSCSI0")

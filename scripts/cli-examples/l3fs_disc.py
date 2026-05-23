"""Build a bootable Level 3 File Server hard disc image end-to-end.

The recipe runs as one coherent sequence — every step shares the
working directory and the scsi0.dat image with the next — but its
output is split into four named sections via `section()` so the
cookbook page can interleave each section with explanatory prose
without rebuilding state.

Sections:

  envelope     Create the empty ADFS hard-disc envelope.
  install_fs   Copy the file-server binary across from its SSD.
  boot         Write !BOOT and set the boot option (read + set).
  attach_afs   Plan + initialise the AFS partition + verify users.
  verify       Final stat showing the dual-partition shape.

The source SSD with the FS executable lives in the cookbook corpus
at tests/data/images/cookbook/FS3v126.ssd.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "cookbook" / "FS3v126.ssd"

with in_tmp_dir():
    shutil.copy(SOURCE, "FS3v126.ssd")

    section("envelope")
    show("disc create scsi0.dat --format adfs-hard --capacity 10MB --title Server")

    section("install_fs")
    show("disc cp 'FS3v126.ssd:$.FS3v126' 'scsi0.dat:$.FS3v126'")

    section("boot")
    show("printf '*RUN $.FS3v126\\r' | disc put 'scsi0.dat:$.!BOOT' -")
    show("disc opt scsi0.dat")
    show("disc opt scsi0.dat EXEC")

    section("attach_afs")
    show("disc afs-plan scsi0.dat")
    show(
        "disc afs-init scsi0.dat --disc-name Server"
        " --user RJS:2MB"
        " --omit-user Welcome"
        " --emplace Library --emplace Library1"
    )
    show("disc afs-users scsi0.dat")

    section("verify")
    show("disc stat scsi0.dat")

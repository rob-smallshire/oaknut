"""Build a bootable Level 3 File Server hard disc image end-to-end.

The recipe runs as one coherent sequence — every step shares the
working directory and the scsi0.dat image with the next — but its
output is split into four named sections via `section()` so the
cookbook page can interleave each section with explanatory prose
without rebuilding state.

Sections:

  envelope     Create the empty ADFS hard-disc envelope.
  install_fs   Copy the file-server binary across from its SSD.
  startup      Tokenise and store StartFS, a BASIC program that answers
               the server's start-up questions unattended. Its source is
               sources/StartFS.bas, shown on the page by literalinclude.
  boot         Write a !BOOT that chains StartFS; set the boot option.
  plan_afs     Dry-run sizing of the AFS partition (afs-plan).
  init_afs     Carve out the AFS partition for real (afs-init).
  inspect_afs  Confirm the resulting user list (afs-users).
  populate_afs Copy files from a floppy into a user's directory and the library.
  verify       Final stat showing the dual-partition shape.

The source SSD is the Level 3 File Server 1.26 release disc,
l3v126.ssd, from https://github.com/mmbeeb/L3V126/releases/tag/MML3V126,
kept unmodified in the cookbook corpus. Its executable is $.FS; the
recipe installs it as $.FS3v126, the name the community conventionally
gives the 1.26 file server so its version is plain.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "tests" / "data" / "images" / "cookbook" / "l3v126.ssd"
# The start-up program's host source; the cookbook page shows this same
# file with a literalinclude, so the text cannot drift from what runs.
STARTFS_SOURCE = Path(__file__).resolve().parent / "sources" / "StartFS.bas"

with in_tmp_dir():
    shutil.copy(SOURCE, "l3v126.ssd")
    shutil.copy(STARTFS_SOURCE, "StartFS.bas")

    section("envelope")
    show("disc create scsi0.dat --geometry capacity=10MB --title Server")

    section("install_fs")
    show("disc cp 'l3v126.ssd:$.FS' 'scsi0.dat:$.FS3v126'")

    section("startup")
    show(
        "oaknut-basic tokenise StartFS.bas"
        " | disc put 'scsi0.dat:$.StartFS' --load 0xFFFF1900 --exec 0xFFFF8023"
    )

    section("boot")
    show("printf 'CHAIN\"StartFS\"\\r' | disc put 'scsi0.dat:$.!BOOT' -")
    show("disc opt scsi0.dat")
    show("disc opt scsi0.dat EXEC")

    section("plan_afs")
    show("disc afs plan scsi0.dat")

    section("init_afs")
    show(
        "disc afs init scsi0.dat --disc-name Server"
        " --user RJS:2MB"
        " --omit-user Welcome"
        " --emplace Library --emplace Library1"
    )

    section("inspect_afs")
    show("disc afs users scsi0.dat")

    section("populate_afs")
    show("disc create saves.ssd")
    show("printf 'Commander Jameson' | disc put 'saves.ssd:$.MAX' -")
    show("printf 'tool' | disc put 'saves.ssd:$.TOOL' -")
    show("disc cp 'saves.ssd:$.MAX' 'scsi0.dat:afs:$.RJS.Saves.MAX'")
    show("disc tree 'scsi0.dat:afs:$.RJS'")
    show("disc cp 'saves.ssd:$.TOOL' 'scsi0.dat:afs:$.Library.Tool' --access R/R")
    show("disc stat 'scsi0.dat:afs:$.Library.Tool'")

    section("verify")
    show("disc stat scsi0.dat")
    show("disc tree scsi0.dat")

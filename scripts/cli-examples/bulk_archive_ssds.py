"""Archive a folder of SSDs into per-disc subdirectories on one ADFS disc.

A pragmatic real-world recipe: you have a folder of DFS .ssd files
on your host and want them all sitting on a single ADFS hard disc,
each under its own directory named for the source. A ``for`` loop
over the SSDs, with ``disc cp -r`` per iteration, does the work in
three lines of shell.

Sections:

  sources     ``ls *.ssd`` — show the host-side filenames the loop
              will iterate over.
  loop        The for-loop that walks the SSDs and bulk-copies.
  verify      List the top level of the archive, then walk the tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GAMES_DIR = REPO_ROOT / "tests" / "data" / "images" / "games"

with in_tmp_dir():
    # Bring three SSDs into the working directory so the for-loop has
    # files to iterate over without dragging an absolute path into the
    # captured command line.
    silent(f"cp {GAMES_DIR}/Disc00*.ssd .")
    silent("disc create archive.dat --format adfs-hard --capacity 10MB --title GamesArchive")

    section("sources")
    show("ls *.ssd")

    section("loop")
    # `cut -d- -f1` takes the disc-number prefix ("Disc001",
    # "Disc002", "Disc003") as the directory name — short, ordered,
    # and well within ADFS's 10-character filename limit. The full
    # game titles stay visible in the source filenames the previous
    # section listed.
    #
    # `disc cp -r` auto-creates the destination directory if it does
    # not exist, matching Unix `cp -r SRC DEST` — no explicit
    # `disc mkdir` is needed.
    show(
        'for ssd in *.ssd; do\n'
        '  name="$(basename "$ssd" .ssd | cut -d- -f1)"\n'
        '  disc cp -r "$ssd:\\$" "archive.dat:\\$.$name"\n'
        'done'
    )

    section("verify")
    show("disc ls archive.dat")
    show("disc tree archive.dat")

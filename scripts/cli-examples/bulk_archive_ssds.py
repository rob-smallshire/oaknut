"""Archive a folder of SSDs into per-disc subdirectories on one ADFS disc.

A pragmatic real-world recipe: you have a folder of DFS .ssd files
on your host and want them all sitting on a single ADFS hard disc,
each under its own directory named for the source. A ``for`` loop
over the SSDs, with ``disc mkdir`` + ``disc cp -r`` per iteration,
does the work in a few lines of shell.

Sections:

  setup       Stage three SSDs from the test fixtures and create
              the empty ADFS hard-disc archive. (silent — fixture work)
  loop        The for-loop that walks the SSDs and bulk-copies.
  verify      List the top level of the archive to confirm.
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

    section("loop")
    # The sed expression strips the leading "DiscNNN-" disc-number
    # prefix and keeps the first CamelCase word that follows. For
    # the three SSDs below this yields "Planetoid", "Arcadians",
    # "Zalaga" — all human-readable and well inside ADFS's 10-char
    # filename budget. (A simple `cut -c1-10` would land arbitrary
    # truncations like "Disc001-Pl".)
    #
    # `disc cp -r` auto-creates the destination directory if it does
    # not exist, matching Unix `cp -r SRC DEST` — no explicit
    # `disc mkdir` is needed.
    show(
        'for ssd in *.ssd; do\n'
        "  name=\"$(basename \"$ssd\" .ssd | sed -E 's/^[^-]+-([A-Z][a-z]+).*/\\1/')\"\n"
        '  disc cp -r "$ssd:\\$" "archive.dat:\\$.$name"\n'
        'done'
    )

    section("verify")
    show("disc ls archive.dat")
    show("disc tree archive.dat")

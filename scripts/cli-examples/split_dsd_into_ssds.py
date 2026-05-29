"""Split a double-sided DSD back into two single-sided SSDs.

The inverse of :doc:`assembling a DSD <assemble_dsd_from_ssds>`: a
double-sided ``.dsd`` carries two independent DFS volumes, and this
recipe lifts each side out into its own single-sided ``.ssd``. Side 0 is
the default; side 2 is reached with the Acorn drive prefix ``::2``.

The starting DSD is built silently from two shipped game SSDs so the
recipe is self-contained; the shown steps are the split itself.

Sections:

  source    ``disc stat`` — the two-sided source DSD, each side listed
            under its drive designation (``:0`` / ``:2``).
  create    ``disc create`` — two blank single-sided SSDs to receive
            the sides.
  extract   One ``disc cp`` per side: side 0 out to one SSD, side 2 out
            to the other.
  verify    ``disc ls`` — each extracted SSD holds exactly one side.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GAMES_DIR = REPO_ROOT / "tests" / "data" / "images" / "games"

with in_tmp_dir():
    # Build the two-sided source DSD silently — Arcadians on side 0,
    # Zalaga on side 2 — so the recipe starts from a populated disc.
    silent(f"cp {GAMES_DIR}/Disc002-Arcadians.ssd arcadians.ssd")
    silent(f"cp {GAMES_DIR}/Disc003-Zalaga.ssd zalaga.ssd")
    silent("disc create compendium.dsd --title Arcadians")
    silent("disc cp 'arcadians.ssd:$.*' 'compendium.dsd:$/'")
    silent("disc cp 'zalaga.ssd:$.*' 'compendium.dsd::2.$/'")
    silent("disc title 'compendium.dsd::2' Zalaga")

    section("source")
    show("disc stat compendium.dsd")

    section("create")
    show("disc create side-0.ssd")
    show("disc create side-2.ssd")

    section("extract")
    # Side 0 is the default — no drive prefix. Side 2 is ::2. The `$.*`
    # glob lifts every file out of each side's `$` directory into the
    # target SSD's `$`.
    show("disc cp 'compendium.dsd:$.*' 'side-0.ssd:$/'")
    show("disc cp 'compendium.dsd::2.$.*' 'side-2.ssd:$/'")

    section("verify")
    show("disc ls side-0.ssd:\\$")
    show("disc ls side-2.ssd:\\$")

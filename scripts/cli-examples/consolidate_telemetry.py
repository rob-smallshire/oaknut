"""Consolidate four months of Acorn DFS telemetry onto one Watford disc.

Daily temperature readings are stored one file per day. A month runs to
31 days — exactly Acorn DFS's per-disc file limit — so each month of 1984
fills its own single-sided Acorn floppy. Watford DFS extends the
catalogue to 62 files per side, so a single double-sided Watford disc
holds all four months: two to a side. This copies from one DFS variant
to another and exercises the larger Watford catalogue.

Sections:

  inputs    The four monthly Acorn discs, a day's hourly readings, and
            one month's catalogue — 31 files, Acorn's ceiling.
  create    ``disc create --filesystem watford-dfs`` — a blank
            double-sided Watford disc.
  copy      Two months onto each side (drive ``:0`` and drive ``:2``).
  title     Name each side for its quarter-half.
  verify    ``disc stat`` — 60 and 61 files a side, past Acorn's 31.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TELEMETRY_DIR = REPO_ROOT / "tests" / "data" / "images" / "telemetry"

with in_tmp_dir():
    silent(f"cp {TELEMETRY_DIR}/telem-84*.ssd .")

    section("inputs")
    # Four single-sided Acorn floppies, one month each.
    show("ls *.ssd")
    # A day's file: 24 hourly temperatures (deg C), carriage-return separated.
    show("disc cat telem-8401.ssd:$.840115")
    # January fills the disc to Acorn's 31-file limit.
    show("disc stat telem-8401.ssd")

    section("create")
    # A Watford disc holds 62 files per side — room for two months.
    show("disc create telem.dsd --filesystem watford-dfs")

    section("copy")
    # Two months onto side 0, two onto side 2. The `$.*` glob takes every
    # day file; the trailing `.` is the Acorn directory marker on the
    # destination.
    show("disc cp 'telem-8401.ssd:$.*' 'telem.dsd::0.$.'")
    show("disc cp 'telem-8402.ssd:$.*' 'telem.dsd::0.$.'")
    show("disc cp 'telem-8403.ssd:$.*' 'telem.dsd::2.$.'")
    show("disc cp 'telem-8404.ssd:$.*' 'telem.dsd::2.$.'")

    section("title")
    # Watford titles are 10 characters; name each side for the months it holds.
    show("disc title 'telem.dsd::0' 'Jan-Feb 84'")
    show("disc title 'telem.dsd::2' 'Mar-Apr 84'")

    section("verify")
    show("disc stat telem.dsd")

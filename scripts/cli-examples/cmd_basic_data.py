"""Recipe for the ``oaknut-basic data`` subcommands.

Sections:

  encode   Build a tagged data file from a JSON array of values.
  inspect  Show the records in a data file as a table.
  decode   Turn a data file back into a JSON array (round-trips encode).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

_VALUES = '[42, "HELLO", 3.5]'

with in_tmp_dir():
    section("encode")
    show(f"echo '{_VALUES}' | oaknut-basic data encode - SCORES")

    section("inspect")
    silent(f"echo '{_VALUES}' | oaknut-basic data encode - SCORES")
    show("oaknut-basic data inspect SCORES --as display")

    section("decode")
    silent(f"echo '{_VALUES}' | oaknut-basic data encode - SCORES")
    show("oaknut-basic data decode SCORES")

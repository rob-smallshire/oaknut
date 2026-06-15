"""Recipe for ``oaknut-basic detokenise``.

Sections:

  detokenise  Turn a stored, tokenised program back into a numbered
              listing. The program is built first with `tokenise`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

with in_tmp_dir():
    section("detokenise")
    silent("printf '10 PRINT \"HELLO\"\\n20 GOTO 10\\n' | oaknut-basic tokenise > PROG")
    show("oaknut-basic detokenise --encoding utf-8 PROG")

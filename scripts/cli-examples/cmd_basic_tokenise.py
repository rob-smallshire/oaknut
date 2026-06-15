"""Recipe for ``oaknut-basic tokenise``.

Sections:

  tokenise         Numbered source in, tokenised program out (shown as
                   hex bytes so the binary is readable).
  auto             Auto-number unnumbered source with --start, proven by
                   de-tokenising the result back to a numbered listing.
  roundtrip        tokenise then detokenise reproduces the source.
  already-numbered Auto-numbering already-numbered source is an error.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, show_error  # noqa: E402

with in_tmp_dir():
    section("tokenise")
    # The tokenised program is binary; pipe through `od` to show the bytes:
    # the &0D line markers, the keyword tokens, and the &0D &FF end marker.
    show("printf '10 PRINT\\n20 END\\n' | oaknut-basic tokenise | od -An -tx1")

    section("auto")
    # Unnumbered source, numbered as if typed under AUTO, then read back.
    show(
        "printf 'PRINT\\nEND\\n' | oaknut-basic tokenise --start 10 "
        "| oaknut-basic detokenise --encoding utf-8"
    )

    section("roundtrip")
    show(
        "printf '10 PRINT\\n20 GOTO 10\\n' "
        "| oaknut-basic tokenise --encoding utf-8 "
        "| oaknut-basic detokenise --encoding utf-8"
    )

    section("already-numbered")
    show_error("printf '10 PRINT\\n' | oaknut-basic tokenise --start 10")

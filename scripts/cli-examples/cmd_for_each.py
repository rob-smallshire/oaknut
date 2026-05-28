"""Examples for ``disc for-each`` — one transcript per ``--mode`` value.

Built as four named sections so the command-reference page can show each
mode under its own short prose intro via ``:section:``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, section, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.ssd --title Demo")
    silent("printf 'hello' | disc put 'demo.ssd:$.A' -")
    silent("printf 'world!' | disc put 'demo.ssd:$.B' -")
    silent("printf 'goodbye' | disc put 'demo.ssd:$.C' -")

    # Default mode: each file's bytes piped to the command's stdin.
    section("content")
    show(
        "disc for-each 'demo.ssd:*' -- "
        "python3 -c 'import sys, hashlib; "
        "print(hashlib.md5(sys.stdin.buffer.read()).hexdigest())'"
    )

    # inner-path: the in-image path string is substituted into {} per
    # match (or appended, find-style). `echo` just prints its argument,
    # so the output column carries the path verbatim — handy for
    # filename templating, logging, or any tool that takes a path as a
    # string and does not need to open it.
    section("inner-path")
    show("disc for-each 'demo.ssd:*' --mode inner-path -- echo")

    # compound-path: the full OUTER:INNER is substituted, which lets
    # `disc` itself act as the per-file action — the rest of the CLI
    # composes for free.
    section("compound-path")
    show("disc for-each 'demo.ssd:*' --mode compound-path -- disc cat {}")

    # materialise: each file's bytes are written to a host temp file and
    # its path substituted, so tools that only take regular files
    # (file(1), image viewers, emulators) can be pointed at in-image
    # contents without a manual extract step.
    section("materialise")
    show("disc for-each 'demo.ssd:*' --mode materialise -- file {}")

"""Example for ``disc for-each`` — pipe each matching file's bytes through a command.

The headline use case: a TSV of (path, computed-result) without ever
landing the file's bytes on the host. Uses a tiny Python invocation
instead of ``md5sum`` so the example renders identically on macOS and
Linux. The ``sh -c`` wrapper trims md5sum's trailing ``  -`` stdin
marker — for cleaner TSV the user composes the command as usual.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli_example_helper import in_tmp_dir, show, silent  # noqa: E402

with in_tmp_dir():
    silent("disc create demo.ssd --title Demo")
    silent("printf 'hello' | disc put 'demo.ssd:$.A' -")
    silent("printf 'world!' | disc put 'demo.ssd:$.B' -")
    silent("printf 'goodbye' | disc put 'demo.ssd:$.C' -")

    # Default mode: each file's bytes piped to the command's stdin.
    show(
        "disc for-each 'demo.ssd:*' -- "
        "python3 -c 'import sys, hashlib; "
        "print(hashlib.md5(sys.stdin.buffer.read()).hexdigest())'"
    )

    # `--mode compound-path`: each match's full IMAGE:PATH is substituted for
    # {}, so the disc CLI itself becomes the per-file action language.
    show("disc for-each 'demo.ssd:*' --mode compound-path -- disc cat {}")

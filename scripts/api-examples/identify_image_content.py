"""Identify a disc image's filesystem(s) by content, not by extension.

The same content-first detection the ``disc identify`` CLI command
uses. Returns a list of :class:`~oaknut.filesystem.Identification`
candidates ranked best-first; each carries a
:class:`~oaknut.filesystem.Confidence` and, for a host disc, any
contained sub-partitions (a combined ADFS + AFS hard disc reports the
ADFS host with the AFS tail in ``contained``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.dfs import DFS
from oaknut.filesystem import identify


def report_identification(filepath: Path) -> None:
    """Print the identification tree for *filepath*, best-first.

    A bare summary line per candidate plus an indented line per
    contained sub-partition. The recipe walks one level of nesting —
    enough for ADFS + AFS — but ``contained`` is a tree, so a deeper
    walk just recurses.

    Args:
        filepath: Any disc image. Returns silently with a "nothing
            recognised" message if no installed filesystem matches.
    """
    candidates = identify(filepath)
    if not candidates:
        print(f"{filepath.name}: nothing recognised")
        return
    for host in candidates:
        print(f"{host.confidence.name:8s} {host.filesystem}")
        for nested in host.contained:
            print(
                f"         └─ {nested.confidence.name:8s} "
                f"{nested.filesystem} ({nested.partition.selector})"
            )


def _build_demo_disc(workdir: Path) -> Path:
    """Build a fresh DFS image so the recipe runs without external corpus."""
    filepath = workdir / "demo.ssd"
    with DFS.create_file(filepath, title="Demo"):
        pass
    return filepath


def main(workdir: Path) -> None:
    """Run the recipe against a freshly-built demo disc."""
    report_identification(_build_demo_disc(workdir))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))

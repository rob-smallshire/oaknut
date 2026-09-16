"""Unified CLI for Acorn DFS, ADFS, and AFS disc images."""

__version__ = "12.18.1"

from oaknut.disc.cli import gather  # noqa: E402  (needs __version__ defined first)

__all__ = ["gather"]

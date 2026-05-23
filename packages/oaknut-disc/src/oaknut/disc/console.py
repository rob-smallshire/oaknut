"""Colour-aware console output helpers for the ``disc`` CLI.

These helpers are the bridge between ``oaknut.exception``'s structured
error rendering and the user's terminal. They all write to stderr —
stdout is reserved for the command's normal report output so that
``disc cmd ... | jq .`` keeps working even when the command reports
errors mid-stream.

Three audience levels:

- :func:`print_error` — red, for failures (``handled_errors``'s
  printer).
- :func:`print_warning` — yellow, for "this worked, but you should
  know" notes.
- :func:`print_info` — cyan, for incidental progress chatter.

Colour is suppressed automatically when stderr is not a terminal, when
the ``NO_COLOR`` environment variable is set (the cross-tool
convention), or when ``CLICOLOR=0`` is set.
"""

from __future__ import annotations

import os
import sys

import click

__all__ = [
    "print_error",
    "print_warning",
    "print_info",
    "colour_enabled",
]


def colour_enabled() -> bool:
    """Return whether stderr is allowed to carry ANSI colour codes.

    Honours :envvar:`NO_COLOR` (any non-empty value disables) and
    :envvar:`CLICOLOR` (``0`` disables), with a final TTY check.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("CLICOLOR") == "0":
        return False
    return sys.stderr.isatty()


def print_error(line: str, is_continuation: bool = False) -> None:
    """Write *line* to stderr in red (leaf) or muted yellow (continuation).

    The signature matches :class:`oaknut.exception.Printer` so this can
    be passed directly to :func:`oaknut.exception.handled_errors`.

    Leaf messages — the head of an exception's render — get red. Notes
    and cause-chain entries get a muted yellow so the reader can see
    they are *context for* the leaf without competing for attention.
    """
    colour = colour_enabled()
    if is_continuation:
        if colour:
            click.secho(line, err=True, fg="yellow")
        else:
            click.echo(line, err=True)
        return

    prefix = "Error: "
    if colour:
        click.secho(prefix, err=True, fg="red", bold=True, nl=False)
        click.secho(line, err=True, fg="red")
    else:
        click.echo(prefix + line, err=True)


def print_warning(line: str) -> None:
    """Write *line* to stderr in magenta (or plain when colour is off)."""
    if colour_enabled():
        click.secho(line, err=True, fg="magenta")
    else:
        click.echo(line, err=True)


def print_info(line: str) -> None:
    """Write *line* to stderr in cyan (or plain when colour is off)."""
    if colour_enabled():
        click.secho(line, err=True, fg="cyan")
    else:
        click.echo(line, err=True)

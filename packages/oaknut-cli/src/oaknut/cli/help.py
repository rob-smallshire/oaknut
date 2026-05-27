"""Terminal-friendly help: strip RST inline markup as Click renders it.

Command docstrings and option help are dual-purpose — Click prints them
verbatim at the terminal, while the ``disc`` Sphinx command reference
renders them as reStructuredText. RST inline markup (``literal`` spans)
that reads as code in the manual shows as stray backticks in a terminal.

:func:`use_plain_help` makes a command (and, for a group, its whole
subtree) render help through a formatter that reduces that markup to
plain text at display time, leaving the docstrings untouched for Sphinx.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import click

__all__ = ["strip_rst", "PlainHelpFormatter", "use_plain_help"]

# ``literal`` and `interpreted` spans — one or two backticks either side.
_BACKTICK_SPAN = re.compile(r"`{1,2}([^`]+)`{1,2}")


def strip_rst(text: str) -> str:
    """Reduce the RST inline markup used in help text to plain text.

    ``code`` and `code` both collapse to ``code`` — readable at a
    terminal. Only backtick spans are touched; everything else is left
    as written.
    """
    return _BACKTICK_SPAN.sub(r"\1", text)


class PlainHelpFormatter(click.HelpFormatter):
    """A Click help formatter that strips RST markup as it writes.

    Every piece of help text — the body paragraphs (:meth:`write_text`)
    and the option / subcommand definition lists (:meth:`write_dl`) —
    passes through :func:`strip_rst` on the way out.
    """

    def write_text(self, text: str) -> None:
        super().write_text(strip_rst(text))

    def write_dl(
        self, rows: Iterable[tuple[str, str]], *args: object, **kwargs: object
    ) -> None:
        super().write_dl(
            [(strip_rst(term), strip_rst(definition)) for term, definition in rows],
            *args,
            **kwargs,
        )


class _PlainHelpContext(click.Context):
    """A Click context whose help is formatted by :class:`PlainHelpFormatter`."""

    formatter_class = PlainHelpFormatter


def use_plain_help(command: click.Command) -> None:
    """Render *command*'s help with RST markup stripped.

    For a group, applies to the whole subtree, so a single call on a
    fully-assembled CLI covers every subcommand — including ones
    contributed by other packages, regardless of how they were built.
    """
    command.context_class = _PlainHelpContext
    if isinstance(command, click.Group):
        for sub in command.commands.values():
            use_plain_help(sub)

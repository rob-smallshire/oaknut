"""The ``--meta-format`` choice shared by every host-boundary command."""

from __future__ import annotations

import click
from oaknut.file import DEPRECATED_META_FORMATS, MetaFormat

#: The choice meaning "carry no metadata", alongside the MetaFormat values.
META_FORMAT_NONE = "none"


class MetaFormatChoice(click.Choice):
    """A case-insensitive choice of :class:`~oaknut.file.MetaFormat` values or ``none``.

    The choices follow :class:`~oaknut.file.MetaFormat`, so a new format
    reaches every command at once. A deprecated name from
    :data:`~oaknut.file.DEPRECATED_META_FORMATS` is accepted, with a
    warning on stderr, and converts to the name that replaces it; it is
    not listed in help.
    """

    def __init__(self) -> None:
        super().__init__([*(f.value for f in MetaFormat), META_FORMAT_NONE], case_sensitive=False)

    def convert(self, value, param, ctx):
        if isinstance(value, str):
            replacement = DEPRECATED_META_FORMATS.get(value.lower())
            if replacement is not None:
                click.echo(
                    f"warning: --meta-format {value} is deprecated; use {replacement.value}.",
                    err=True,
                )
                value = replacement.value
        return super().convert(value, param, ctx)

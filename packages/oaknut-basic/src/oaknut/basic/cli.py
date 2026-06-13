"""Click command-line interface for BBC BASIC tools.

A standalone ``oaknut-basic`` entry point in the style of the unified
``disc`` CLI: Click for command parsing, asyoulikeit for formatted
output, and the shared :func:`oaknut.exception.handled_errors` boundary
so categorised errors surface as clean messages rather than tracebacks.

This module imports Click and is loaded only when ``oaknut-basic`` is
installed with its ``[cli]`` extra; the library core never imports it.
"""

from __future__ import annotations

import click

from . import __version__


class _BasicGroup(click.Group):
    """Click group applying the oaknut error boundary to every command.

    Wrapping :meth:`invoke` means each subcommand is guarded once, with
    no per-command decorator: categorised
    :class:`~oaknut.exception.DataError` /
    :class:`~oaknut.exception.ConfigurationError` are printed and turned
    into the matching exit code. ``--debug`` re-raises them with a full
    traceback for development.
    """

    def invoke(self, ctx: click.Context):
        from oaknut.exception import handled_errors

        debug = bool(ctx.params.get("debug", False))
        with handled_errors(debug=debug):
            return super().invoke(ctx)


@click.group(cls=_BasicGroup)
@click.version_option(__version__, prog_name="oaknut-basic")
@click.option(
    "--debug",
    is_flag=True,
    hidden=True,
    help="Re-raise data and configuration errors with a full traceback.",
)
def cli(debug: bool) -> None:  # noqa: ARG001 - read by the group error boundary
    """Tools for BBC BASIC source and tokenised programs."""


def _validate_encoding(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """Reject an unknown ``--encoding`` with a clean usage error.

    Importing :mod:`oaknut.file` first registers the ``"acorn"`` codec,
    so it resolves alongside the stdlib encodings.
    """
    import codecs

    import oaknut.file  # noqa: F401 - registers the "acorn" codec as a side effect

    try:
        codecs.lookup(value)
    except LookupError:
        raise click.BadParameter(f"unknown encoding: {value!r}") from None
    return value


@cli.command()
@click.argument(
    "input_stream",
    metavar="[INPUT]",
    type=click.File("rb"),
    default="-",
    required=False,
)
@click.argument(
    "output_stream",
    metavar="[OUTPUT]",
    type=click.File("wb"),
    default="-",
    required=False,
)
@click.option(
    "--encoding",
    default="utf-8",
    show_default=True,
    callback=_validate_encoding,
    help='Text encoding of INPUT and OUTPUT. Use "acorn" for the BBC '
    "character set (CR line endings) when writing to a disc image.",
)
@click.option(
    "--start",
    type=click.IntRange(min=0),
    default=10,
    show_default=True,
    help="Line number given to the first line.",
)
@click.option(
    "--step",
    type=click.IntRange(min=1),
    default=10,
    show_default=True,
    help="Increment between successive line numbers.",
)
def number(input_stream, output_stream, encoding: str, start: int, step: int) -> None:
    """Prepend ascending line numbers to an unnumbered BBC BASIC program.

    Reads BASIC source text from INPUT and writes the numbered program
    to OUTPUT. Both default to ``-``: INPUT to standard input, OUTPUT to
    standard output, so the command works file-to-file ::

        oaknut-basic number menu.bas menu-numbered.bas

    and as a pipe stage between ``disc get`` and ``disc put`` ::

        disc get game.ssd MENU - | oaknut-basic number --encoding acorn | disc put game.ssd MENU -

    Text is read and written in ``--encoding`` (``utf-8`` by default; pass
    ``acorn`` for the BBC character set). Input line endings are accepted
    in any of the ``\\n`` / ``\\r`` / ``\\r\\n`` forms; output uses the
    Acorn-native ``\\r`` under the ``acorn`` encoding and ``\\n``
    otherwise.

    Line numbering mirrors the BBC's ``AUTO start,step``: internal
    references such as ``GOTO`` are left untouched, so they must already
    match the numbering requested here.
    """
    import codecs

    from oaknut.basic import number_lines
    from oaknut.file import decode_text, encode_text

    line_terminator = "\r" if codecs.lookup(encoding).name == "acorn" else "\n"
    source = decode_text(input_stream.read(), encoding=encoding)
    numbered = number_lines(source, start=start, step=step)
    output_stream.write(encode_text(numbered, encoding=encoding, newline=line_terminator))


if __name__ == "__main__":  # pragma: no cover
    cli()

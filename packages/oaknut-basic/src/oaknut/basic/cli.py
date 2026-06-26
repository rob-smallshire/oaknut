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
from asyoulikeit.cli import report_output

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
    """Tools for BBC BASIC programs and data files."""


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


def _source_to_code_points(data: bytes, encoding: str) -> str:
    """Return the latin-1 code-point view of source text's Acorn bytes.

    The tokeniser treats each character's code point as a raw byte, so
    the CLI normalises the input encoding to Acorn bytes here. Under the
    default ``acorn`` encoding the input is already Acorn bytes and is
    passed through untouched; otherwise it is decoded and re-encoded to
    the BBC character set.
    """
    import codecs

    import oaknut.file  # noqa: F401 - registers the "acorn" codec

    if codecs.lookup(encoding).name == "acorn":
        acorn_bytes = data
    else:
        acorn_bytes = data.decode(encoding).encode("acorn")
    return acorn_bytes.decode("latin-1")


def _listing_to_bytes(listing: str, encoding: str) -> bytes:
    """Encode a de-tokenised listing into output bytes in *encoding*.

    The listing's characters are Acorn code points separated by ``\\n``.
    Under ``acorn`` the newlines become the Acorn-native ``\\r``;
    otherwise the Acorn bytes are transcoded to *encoding*, keeping
    ``\\n``.
    """
    import codecs

    import oaknut.file  # noqa: F401 - registers the "acorn" codec

    if codecs.lookup(encoding).name == "acorn":
        return listing.replace("\n", "\r").encode("latin-1")
    return listing.encode("latin-1").decode("acorn").encode(encoding)


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
    help='Text encoding of the INPUT source. Use "acorn" for the BBC '
    "character set (e.g. source taken straight off a disc image).",
)
@click.option(
    "--start",
    type=click.IntRange(min=0),
    default=None,
    help="Auto-number from this line (as AUTO would); INPUT must be unnumbered. "
    "Defaults to 10 when only --step is given.",
)
@click.option(
    "--step",
    type=click.IntRange(min=1),
    default=None,
    help="Auto-numbering increment. Defaults to 10 when only --start is given.",
)
def tokenise(
    input_stream, output_stream, encoding: str, start: int | None, step: int | None
) -> None:
    """Tokenise BBC BASIC source text into a stored program.

    Reads numbered BASIC source from INPUT and writes the tokenised
    program bytes to OUTPUT. Both default to ``-`` (stdin / stdout), so it
    drops in alongside ``disc put`` ::

        oaknut-basic tokenise menu.bas MENU
        cat menu.bas | oaknut-basic tokenise | disc put game.ssd MENU -

    Passing --start and/or --step auto-numbers unnumbered source, exactly
    as typing it under ``AUTO`` would; it is an error to use them on source
    that already carries line numbers ::

        oaknut-basic tokenise --start 10 unnumbered.bas MENU

    INPUT is read in --encoding (``utf-8`` by default, for source authored
    in a modern editor; pass ``acorn`` for the BBC character set, e.g.
    source taken straight off a disc image).
    """
    from oaknut.basic import tokenise as tokenise_source

    source = _source_to_code_points(input_stream.read(), encoding)
    output_stream.write(tokenise_source(source, start=start, step=step))


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
    help='Text encoding for the OUTPUT source. Use "acorn" for the BBC '
    "character set with CR line endings (e.g. writing back to a disc image).",
)
@click.option(
    "--dialect",
    type=click.Choice(["ii", "v"]),
    default="ii",
    show_default=True,
    help='BBC BASIC dialect. Use "v" for Archimedes / RISC OS programs, so the '
    "&C6/&C7/&C8 escape tokens (CASE, SYS, ORIGIN, ...) decode correctly.",
)
def detokenise(input_stream, output_stream, encoding: str, dialect: str) -> None:
    """De-tokenise a stored BBC BASIC program into source text.

    Reads a tokenised program from INPUT and writes numbered source text
    to OUTPUT. Both default to ``-`` (stdin / stdout), so it drops in
    alongside ``disc get`` ::

        oaknut-basic detokenise MENU menu.bas
        disc get game.ssd MENU - | oaknut-basic detokenise

    OUTPUT is written in --encoding (``utf-8`` with host-native ``LF`` line
    endings by default, for a host text file; pass ``acorn`` for the BBC
    character set with ``CR`` endings, e.g. writing back to a disc image).

    Pass ``--dialect v`` for Archimedes / RISC OS programs (BBC BASIC V),
    whose extended keywords use the &C6/&C7/&C8 two-byte escape tokens.
    """
    from oaknut.basic import BASIC_II, BASIC_V
    from oaknut.basic import detokenise as detokenise_program

    selected_dialect = BASIC_V if dialect == "v" else BASIC_II
    listing = detokenise_program(input_stream.read(), dialect=selected_dialect)
    output_stream.write(_listing_to_bytes(listing, encoding))


@cli.group()
def data() -> None:
    """Read and write BBC BASIC data files (PRINT#/INPUT#/BPUT#/BGET#).

    These commands work with the type-tagged record files BBC BASIC
    creates with ``OPENOUT`` and writes with ``PRINT#``. ``inspect`` shows
    a file's contents as a table; ``decode`` and ``encode`` are a lossless
    JSON round-trip pair for editing and generating such files.
    """


def _kind_of(value: object) -> str:
    """Return the record-type name for a value read from a data file."""
    if isinstance(value, bool):  # pragma: no cover - reader never yields bool
        raise TypeError("unexpected bool from a data file")
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "real"
    return "string"


def _read_records(input_stream, encoding: str):
    """Yield ``(offset, kind, value)`` for each tagged record in a stream."""
    from oaknut.basic.datafile import open as open_datafile

    with open_datafile(input_stream, "r", encoding=encoding) as reader:
        while True:
            offset = reader.tell()
            value = reader.read()
            if value is None:
                return
            yield offset, _kind_of(value), value


@data.command()
@click.argument(
    "input_stream",
    metavar="[INPUT]",
    type=click.File("rb"),
    default="-",
    required=False,
)
@click.option(
    "--encoding",
    default="acorn",
    show_default=True,
    callback=_validate_encoding,
    help="Text encoding of string records. Defaults to the BBC character set.",
)
def decode(input_stream, encoding: str) -> None:
    """Decode a BBC BASIC data file to a JSON array of its values.

    Reads a ``PRINT#``-tagged data file from INPUT and writes a JSON array
    to standard output, one element per record: integers and reals as JSON
    numbers, strings as JSON strings, and raw bytes as ``{"bytes": "hex"}``.
    Reals keep their full ``float`` repr (e.g. ``5.0``) so they round-trip
    back to reals rather than integers ::

        oaknut-basic data decode scores.dat | jq '.[0]'

    The output is consumed by ``oaknut-basic data encode`` to rebuild the
    file byte-for-byte.
    """
    import json

    payload = [value for _offset, _kind, value in _read_records(input_stream, encoding)]
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@data.command()
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
    default="acorn",
    show_default=True,
    callback=_validate_encoding,
    help="Text encoding for string records. Defaults to the BBC character set.",
)
def encode(input_stream, output_stream, encoding: str) -> None:
    """Encode a JSON array of values into a BBC BASIC data file.

    Reads the JSON array produced by ``oaknut-basic data decode`` from
    INPUT and writes the tagged data file to OUTPUT. Each element becomes
    one ``PRINT#`` record: a JSON integer becomes an integer, a JSON
    number with a fractional part a real, a JSON string a string, and
    ``{"bytes": "hex"}`` raw (untagged) bytes ::

        echo '[42, "HELLO", 3.5]' | oaknut-basic data encode - scores.dat

    A hand-authored real must carry a decimal point (``3.0``, not ``3``),
    matching what ``decode`` emits.
    """
    import json

    from oaknut.basic.datafile import open as open_datafile
    from oaknut.exception import DataError

    try:
        payload = json.loads(input_stream.read())
    except json.JSONDecodeError as error:
        raise DataError(f"invalid JSON input: {error}") from error
    if not isinstance(payload, list):
        raise DataError("expected a JSON array of values")

    with open_datafile(output_stream, "w", encoding=encoding) as writer:
        for index, item in enumerate(payload):
            if isinstance(item, bool):
                raise DataError(f"item {index}: BBC BASIC has no boolean type")
            if isinstance(item, int):
                writer.write_int(item)
            elif isinstance(item, float):
                writer.write_float(item)
            elif isinstance(item, str):
                writer.write_str(item)
            elif isinstance(item, dict) and set(item) == {"bytes"}:
                try:
                    writer.write_bytes(bytes.fromhex(item["bytes"]))
                except (ValueError, TypeError) as error:
                    raise DataError(f"item {index}: invalid hex in bytes value") from error
            else:
                raise DataError(f"item {index}: cannot encode JSON value {item!r}")


@data.command()
@click.argument(
    "input_stream",
    metavar="[INPUT]",
    type=click.File("rb"),
    default="-",
    required=False,
)
@click.option(
    "--encoding",
    default="acorn",
    show_default=True,
    callback=_validate_encoding,
    help="Text encoding of string records. Defaults to the BBC character set.",
)
@report_output(reports={"records": "The tagged records in the data file, in order."})
def inspect(input_stream, encoding: str):
    """Show the records in a BBC BASIC data file as a table.

    Reads a ``PRINT#``-tagged data file from INPUT and reports each record
    with its byte offset, type and value ::

        oaknut-basic data inspect scores.dat
        oaknut-basic data inspect scores.dat --as json

    Rendered through the shared report machinery, so ``--as display`` (the
    default at a terminal), ``--as tsv`` (the default in a pipe) and
    ``--as json`` all describe the same records; the JSON form carries the
    faithful values for scripting.
    """
    from asyoulikeit.tabular_data import Importance, Report, Reports, TableContent

    table = TableContent(title="BBC BASIC data file")
    table.add_column("index", "#", header=True)
    table.add_column("type", "Type")
    table.add_column("value", "Value")
    table.add_column("offset", "Offset", importance=Importance.DETAIL)
    for index, (offset, kind, value) in enumerate(_read_records(input_stream, encoding)):
        table.add_row(index=index, type=kind, value=value, offset=offset)
    return Reports(records=Report(data=table))


if __name__ == "__main__":  # pragma: no cover
    cli()

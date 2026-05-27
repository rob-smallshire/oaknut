"""Click command-line interface for the unified disc tool.

Provides a single ``disc`` / ``oaknut-disc`` entry point for working
with Acorn DFS, ADFS, and AFS disc images. See ``docs/dev/cli-design.md``
for the design rationale.
"""

from __future__ import annotations

import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import click
from asyoulikeit import ByAudience
from asyoulikeit.cli import (
    describe_formatter_command,
    describe_report_command,
    list_formatters_command,
    list_reports_command,
    report_output,
)
from exit_codes import ExitCode
from oaknut.cli import contributed_commands
from oaknut.file.capacity import format_capacity
from oaknut.file.exceptions import FSError

from . import __version__
from .cli_identify import (
    describe_format_command,
    identify_command,
    list_formats_command,
)
from .cli_paths import parse_file_spec
from .mount import partition_selectors, resolve_mount

# ---------------------------------------------------------------------------
# Alias-aware Click group
# ---------------------------------------------------------------------------

_ALIASES: dict[str, str] = {}


class AliasGroup(click.Group):
    """Click group that supports star-prefixed Acorn aliases and applies
    the :func:`oaknut.exception.handled_errors` boundary around every
    subcommand.

    Wrapping at the group means every command is automatically wrapped
    once — there is no need for a per-command ``@handled_errors``
    decorator (the visning-style boilerplate). A group-level
    ``--debug`` flag opts into re-raising :class:`DataError` /
    :class:`ConfigurationError` after they have been printed, so a
    developer running ``disc --debug ...`` still sees the full Python
    traceback.
    """

    def _resolve_alias(self, cmd_name: str) -> str | None:
        """Look up an alias, case-insensitively."""
        canonical = _ALIASES.get(cmd_name)
        if canonical is not None:
            return canonical
        return _ALIASES.get(cmd_name.upper())

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        # Try exact match first.
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        # Try alias lookup (case-insensitive).
        canonical = self._resolve_alias(cmd_name)
        if canonical is not None:
            return click.Group.get_command(self, ctx, canonical)
        return None

    def resolve_command(self, ctx: click.Context, args: list[str]):
        # Override to allow aliases to appear in help / error messages.
        cmd_name = args[0] if args else None
        if cmd_name:
            canonical = self._resolve_alias(cmd_name)
            if canonical is not None:
                args = [canonical] + args[1:]
        return super().resolve_command(ctx, args)

    def invoke(self, ctx: click.Context):
        from oaknut.exception import handled_errors

        from .console import print_error

        debug = bool(ctx.params.get("debug", False))
        with handled_errors(print_error, debug=debug):
            return super().invoke(ctx)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """List commands without aliases to keep --help clean."""
        commands = []
        for subcommand in self.list_commands(ctx):
            if subcommand.startswith("*"):
                continue
            cmd = self.commands.get(subcommand)
            if cmd is None:
                continue
            help_text = cmd.get_short_help_str(limit=formatter.width)
            commands.append((subcommand, help_text))

        if commands:
            with formatter.section("Commands"):
                formatter.write_dl(commands)


def _alias(acorn_name: str, unix_name: str) -> None:
    """Register an Acorn star-alias mapping."""
    _ALIASES[acorn_name] = unix_name


def _format_access(access) -> str:
    """Format a wire-form ``oaknut.file.Access`` for display.

    The mounts expose access canonically as a wire-form byte (each
    filesystem maps its own on-disc layout to it — AFS included, issue
    #12), so the CLI formats one representation through the wire renderer.
    """
    from oaknut.file import format_access_text

    return format_access_text(access)


def _access_byte_hex(stat_obj) -> str:
    """Two-digit hex for the canonical wire-form access byte, ``0x``-prefixed.

    Used by ``ls --access-byte`` (issue #10). Every :class:`oaknut.file.Stat`
    exposes ``.access`` as a canonical :class:`oaknut.file.Access` value
    regardless of the underlying filesystem family — for AFS this is the
    wire-form byte its on-disc access translates to (via
    :meth:`AFSAccess.to_acorn`), not the on-disc byte itself, so the
    displayed value round-trips through ``disc chmod path 0x..`` cleanly.

    The ``0x`` prefix makes the value unambiguously hex and directly
    copy-pasteable into ``disc chmod`` — a bare ``13`` would also parse,
    but ``WR`` (also two valid hex digits) would not, so insist on the
    explicit prefix.
    """
    return f"0x{int(stat_obj.access):02X}"


# ---------------------------------------------------------------------------
# DFS format detection (extension + file size)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Image openers — context managers for the format-specific admin commands
# (create / generate-dsc / afs-*) that do not fit the generic mount path.
# ---------------------------------------------------------------------------


@contextmanager
def _adfs_from_file(image_filepath: Path) -> Iterator:
    """Open an ADFS image, translating stdlib OS errors into categorised ones.

    :meth:`ADFS.from_file` raises :class:`FileNotFoundError` when an
    ADFS hard-disc ``.dat`` is missing its companion ``.dsc`` (or
    vice versa). That stdlib error bypasses the CLI's
    :func:`handled_errors` boundary and prints a raw traceback — a
    bug from the user's point of view. Re-raise the same message
    through :class:`ADFSError` so it flows through the categorised
    error pipeline and emerges as a normal ``Error: …`` line.
    """
    from oaknut.adfs import ADFS
    from oaknut.adfs.exceptions import ADFSError

    try:
        with ADFS.from_file(image_filepath) as adfs:
            yield adfs
    except FileNotFoundError as exc:
        # Bare raise (no ``from exc``) so render_error does not echo
        # the same message twice as a "caused by" line — the cause
        # chain still threads through ``__context__`` for --debug.
        raise ADFSError(str(exc)) from None


@contextmanager
def _open_afs(image_filepath: Path) -> Iterator:
    """Open image as ADFS, grab the AFS partition, yield it.

    Raises :class:`AFSNotPresentError` if no AFS partition is
    installed; the CLI :func:`handled_errors` boundary translates
    that to a user-facing message and exit code.
    """
    with (
        _adfs_from_file(image_filepath) as adfs,
        adfs.open_afs_partition() as afs,
    ):
        yield afs


@contextmanager
def open_image_for_afs_write(image_filepath: Path) -> Iterator:
    """Open for AFS write: yields (adfs, afs) with auto-flush on clean exit."""
    with (
        _adfs_from_file(image_filepath) as adfs,
        adfs.open_afs_partition() as afs,
    ):
        yield adfs, afs


def _navigate_afs(afs, bare_path: str):
    """Navigate AFS using its root / operator since AFS.path() may not exist."""
    if bare_path == "$" or not bare_path:
        return afs.root
    # Strip leading "$."
    if bare_path.startswith("$."):
        bare_path = bare_path[2:]
    elif bare_path == "$":
        return afs.root
    target = afs.root
    for part in bare_path.split("."):
        target = target / part
    return target


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group(cls=AliasGroup)
@click.version_option(version=__version__, prog_name="disc")
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help=(
        "Re-raise DataError / ConfigurationError after printing them, "
        "so the full Python traceback is visible. For development; "
        "users should leave this off."
    ),
)
def cli(debug: bool) -> None:
    """Work with Acorn DFS, ADFS, and AFS disc images."""
    # The flag is consumed by AliasGroup.invoke before the subcommand
    # runs; the callback body is intentionally empty.


# "format" is overloaded in this CLI — disc formats (ssd, dsd, adfs-hard, ...)
# are distinct from output formats (display, tsv, json) — so the formatter-
# introspection commands take unambiguous long names.
cli.add_command(list_formatters_command(), name="list-report-formats")
cli.add_command(describe_formatter_command(), name="describe-report-format")

# Companion pair: discover the reports each @report_output command produces.
cli.add_command(list_reports_command(), name="list-reports")
cli.add_command(describe_report_command(), name="describe-report")

# Content-based identification: `identify` answers "what is this image?",
# and the list/describe pair introspects the disc formats it can recognise.
cli.add_command(identify_command(), name="identify")
cli.add_command(list_formats_command(), name="list-formats")
cli.add_command(describe_format_command(), name="describe-format")


# ---------------------------------------------------------------------------
# Inspection commands
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("file_spec")
@click.option(
    "-H",
    "--access-byte",
    "show_access_byte",
    is_flag=True,
    help="Show the raw access byte as two hex digits alongside the symbolic form.",
)
@report_output(reports={"entries": "Directory entries with load/exec/length/attributes."})
def ls(file_spec: str, show_access_byte: bool):
    """List directory contents (Acorn alias: *CAT).

    Accepts a ``FILE_SPEC`` (the in-image ``PATH_SPEC`` is optional and defaults to the root).
    """
    from asyoulikeit.tabular_data import Importance, Report, Reports, TableContent
    from oaknut.file import Access
    from oaknut.filesystem import AcornMetadata, FreeSpace, Titled

    resolved = resolve_mount(file_spec)
    mount = resolved.mount
    target = resolved.path or mount.path_root()

    if not mount.exists(target):
        raise click.ClickException(f"path not found: {target}")

    entry = mount.stat(target)
    if not entry.is_dir:
        # Single file — echo the bare name, pipe-friendly (no header).
        click.echo(entry.name)
        return None

    title_str = mount.title if isinstance(mount, Titled) else ""
    table_title = resolved.image.name
    if title_str:
        table_title += f" — {title_str}"
    # Parentheses, not brackets: the report title is rendered through
    # Rich, which would silently consume ``[name]`` as console markup.
    table_title += f" ({resolved.filesystem})"

    description = (
        f"Free: {mount.free_bytes():,} bytes" if isinstance(mount, FreeSpace) else None
    )

    table = TableContent(title=table_title, description=description)
    table.add_column("name", "Name", header=True)
    # ``type`` discriminates rows so the length column can carry bytes for
    # files and an entry count for directories unambiguously.
    table.add_column("type", "Type")
    # Load/exec are display-focused; drop them from TSV by default so the
    # piped view stays concise. --detailed restores them.
    table.add_column("load", "Load", importance=Importance.DETAIL)
    table.add_column("exec", "Exec", importance=Importance.DETAIL)
    table.add_column("length", "Length")
    table.add_column("attr", "Attr")
    if show_access_byte:
        table.add_column("hex", "Hex")

    has_acorn = isinstance(mount, AcornMetadata)
    for child in mount.iter_entries(target):
        if child.is_dir:
            row = {
                "name": child.name,
                "type": "dir",
                "load": "",
                "exec": "",
                "length": sum(1 for _ in mount.iter_entries(child.path)),
                "attr": "",
            }
            if show_access_byte:
                row["hex"] = ""
            table.add_row(**row)
            continue
        load_cell = exec_cell = attr_str = hex_cell = ""
        if has_acorn:
            meta = mount.acorn_meta(child.path)
            load_cell = _address_cell(meta.load_address)
            exec_cell = _address_cell(meta.exec_address)
            attr_str = _format_access(Access(meta.access))
            hex_cell = f"0x{int(meta.access):02X}"
        row = {
            "name": child.name,
            "type": "file",
            "load": load_cell,
            "exec": exec_cell,
            "length": child.length,
            "attr": attr_str,
        }
        if show_access_byte:
            row["hex"] = hex_cell
        table.add_row(**row)

    return Reports(entries=Report(data=table))


_alias("*CAT", "ls")


@cli.command()
@click.argument("file_spec")
@report_output(reports={"tree": "Hierarchical directory listing."})
def tree(file_spec: str):
    """Display recursive directory tree.

    Accepts a ``FILE_SPEC`` (the in-image ``PATH_SPEC`` is optional and defaults to the root).
    """
    from asyoulikeit.tabular_data import Report, Reports
    from asyoulikeit.tree_data import TreeContent

    _image, path = parse_file_spec(file_spec)

    # The root node carries the image name visibly now that asyoulikeit
    # 0.5.1 drops the Rich-table chrome around single-column trees —
    # setting a TreeContent title would duplicate it.
    tc = TreeContent()
    tc.add_column("name", "Name", header=True)

    if path:
        # Explicit path (possibly with a partition prefix) — that subtree only.
        resolved = resolve_mount(file_spec)
        mount = resolved.mount
        target = resolved.path or mount.path_root()
        if not mount.exists(target):
            raise click.ClickException(f"path not found: {target or '$'}")
        entry = mount.stat(target)
        root = tc.add_root(name=entry.name or resolved.image.name)
        if entry.is_dir:
            _attach_children_mount(mount, target, root)
    else:
        _build_tree_whole_image(file_spec, tc)

    return Reports(tree=Report(data=tc))


def _build_tree_whole_image(file_spec: str, tc) -> None:
    """Populate *tc* with one root per image, labelled partitions beneath.

    Each identified partition is mounted through the coordinator and its
    root contents attached; the partition label is its selector (``adfs``,
    ``afs``, …). A single-partition image folds its contents straight
    under the image root with no partition label.
    """
    image_filepath, _ = parse_file_spec(file_spec)
    selectors = partition_selectors(image_filepath)
    image_root = tc.add_root(name=image_filepath.name)
    multi = len(selectors) > 1
    for selector in selectors:
        resolved = resolve_mount(f"{image_filepath}:{selector}:")
        mount = resolved.mount
        parent = image_root.add_child(name=selector) if multi else image_root
        _attach_children_mount(mount, mount.path_root(), parent)


def _attach_children_mount(mount, path: str, parent_tree_node) -> None:
    """Attach every entry under *path* in *mount*, recursing into directories."""
    for child in mount.iter_entries(path):
        node = parent_tree_node.add_child(name=child.name)
        if child.is_dir:
            _attach_children_mount(mount, child.path, node)


@cli.command()
@click.argument("file_spec")
@report_output(
    reports={
        "disc": (
            "Physical envelope (geometry + total size). Emitted only on a "
            "multi-partition disc (ADFS + AFS), where it carries information "
            "distinct from each partition. Single-partition images fold "
            "this content into ``partition_1``."
        ),
        "partition_1": (
            "First partition's summary. Stands alone (carrying the disc "
            "geometry) on a single-partition image; on a partitioned disc "
            "it is the host slice and ``disc`` carries the geometry."
        ),
        "partition_2": (
            "Second partition (AFS on a partitioned disc; also the report "
            "name when an ``afs:`` prefix scopes the view to that half)."
        ),
        "file": "Per-file metadata when the path denotes a file.",
    }
)
def stat(file_spec: str):
    """Disc summary (no path) or file metadata (with path). Alias: *INFO.

    With no in-partition path, summarises the disc by walking its
    partition structure: a ``disc`` envelope plus one block per
    partition on a partitioned disc, or a single block otherwise. With a
    path, reports that file's metadata.

    Accepts a ``FILE_SPEC`` (the in-image ``PATH_SPEC`` is optional and defaults to the root).
    """
    from asyoulikeit.tabular_data import Report, Reports, TableContent
    from oaknut.file import Access
    from oaknut.filesystem import AcornMetadata

    from .mount import split_selector

    image, in_path = parse_file_spec(file_spec)
    _selector, bare = split_selector(in_path)

    if not bare:
        return _stat_disc(file_spec, image)

    resolved = resolve_mount(file_spec)
    mount = resolved.mount
    if not mount.exists(bare):
        raise click.ClickException(f"path not found: {bare}")
    entry = mount.stat(bare)

    tc = TableContent(title=entry.name, present_transposed=True)
    tc.add_column("name", "Name", header=True)
    row: dict = {"name": entry.name}
    if isinstance(mount, AcornMetadata) and not entry.is_dir:
        meta = mount.acorn_meta(bare)
        tc.add_column("load", "Load")
        row["load"] = _address_cell(meta.load_address)
        tc.add_column("exec", "Exec")
        row["exec"] = _address_cell(meta.exec_address)
        tc.add_column("length", "Length")
        row["length"] = entry.length
        tc.add_column("attr", "Attr")
        row["attr"] = _format_access(Access(meta.access))
    else:
        tc.add_column("length", "Length")
        row["length"] = entry.length
    tc.add_column("dir", "Dir")
    row["dir"] = "yes" if entry.is_dir else "no"
    tc.add_row(**row)
    return Reports(file=Report(data=tc))


_alias("*INFO", "stat")


_SECTOR_SIZE = 256


def _stat_disc(file_spec: str, image_filepath: Path):
    """Summarise a disc by navigating its partition structure.

    A single-partition image yields one ``partition_1`` block carrying
    everything (title, geometry where the filesystem has it, size, free,
    boot). A partitioned disc (ADFS + AFS) yields a ``disc`` envelope
    (the host's physical geometry + total size) plus one block per
    partition; the partition sizes sum to the disc (issue #7). An
    explicit partition prefix scopes the view to that one partition,
    keyed by its position (``afs:`` → ``partition_2``).
    """
    from asyoulikeit.tabular_data import Report, Reports
    from oaknut.filesystem import PhysicalGeometry

    from .mount import split_selector

    selector, _ = split_selector(parse_file_spec(file_spec)[1])
    selectors = partition_selectors(image_filepath)

    if selector is not None:
        # Scoped to one partition — a single block keyed by its position.
        index = selectors.index(selector) if selector in selectors else 0
        resolved = resolve_mount(file_spec)
        block = _partition_block(resolved.mount, selector.upper(), geometry=True)
        return Reports({f"partition_{index + 1}": Report(data=block)})

    if len(selectors) == 1:
        resolved = resolve_mount(f"{image_filepath}:{selectors[0]}:")
        block = _partition_block(resolved.mount, selectors[0].upper(), geometry=True)
        return Reports(partition_1=Report(data=block))

    # Multi-partition: a disc envelope (host geometry) then one block per
    # partition, with cylinder ranges accumulated from each slice's size.
    sections: dict = {}
    host = resolve_mount(f"{image_filepath}:{selectors[0]}:").mount
    disc_geometry = host.disc_geometry() if isinstance(host, PhysicalGeometry) else None
    if disc_geometry is not None:
        sections["disc"] = Report(data=_disc_envelope(disc_geometry))
    spc = disc_geometry.sectors_per_cylinder if disc_geometry else None

    running_cylinder = 0
    for position, selector_name in enumerate(selectors, start=1):
        mount = (
            host
            if selector_name == selectors[0]
            else resolve_mount(f"{image_filepath}:{selector_name}:").mount
        )
        range_text = None
        if spc:
            cylinders = (mount.size_bytes() // _SECTOR_SIZE) // spc
            range_text = f"cylinders {running_cylinder}-{running_cylinder + cylinders - 1}"
            running_cylinder += cylinders
        block = _partition_block(
            mount, f"Partition {position}: {selector_name.upper()}", range_text=range_text
        )
        sections[f"partition_{position}"] = Report(data=block)
    return Reports(sections)


def _disc_envelope(geometry):
    """The ``disc`` envelope block: physical geometry and total size."""
    return _kv_table(
        "Disc",
        [
            ("geometry", "Geometry", geometry.label),
            ("size", "Size", _size_cell(geometry.total_sectors)),
        ],
    )


def _partition_block(mount, title: str, *, geometry: bool = False, range_text: str | None = None):
    """A per-partition summary block assembled from the mount's capabilities.

    *geometry* folds the disc geometry into a single-partition block;
    *range_text* gives the cylinder range on a partitioned disc.
    """
    from oaknut.filesystem import (
        Bootable,
        FreeSpace,
        HierarchicalDirectories,
        PhysicalGeometry,
        Sized,
        Titled,
    )

    pairs: list[tuple[str, str, object]] = []
    if isinstance(mount, Titled) and mount.title:
        pairs.append(("title", "Title", mount.title))
    if geometry and isinstance(mount, PhysicalGeometry):
        pairs.append(("geometry", "Geometry", mount.disc_geometry().label))
    if range_text is not None:
        pairs.append(("range", "Range", range_text))
    if isinstance(mount, Sized):
        pairs.append(("size", "Size", _size_cell(mount.size_bytes() // _SECTOR_SIZE)))
    if isinstance(mount, FreeSpace):
        pairs.append(("free", "Free", _size_cell(mount.free_bytes() // _SECTOR_SIZE)))
    if isinstance(mount, Bootable):
        boot = mount.boot_option
        pairs.append(("boot_option", "Boot option", f"{boot.name} ({boot.value})"))
    if not isinstance(mount, HierarchicalDirectories):
        # A flat catalogue: count the files across its directory letters.
        files = sum(
            1
            for letter in mount.iter_entries(mount.path_root())
            for _ in mount.iter_entries(letter.path)
        )
        pairs.append(("files", "Files", files))
    return _kv_table(title, pairs)


def _size_cell(sectors: int) -> ByAudience:
    """A capacity as an audience-aware cell.

    Humans read friendly IEC units (``800.0 KiB``); machine formatters
    get the raw byte count as an integer, so the presentation base is
    irrelevant to a consumer. Replaces the old composite
    ``"X bytes (Y sectors)"`` string — the sector count is derivable
    from the geometry the same report already carries.
    """
    num_bytes = sectors * _SECTOR_SIZE
    return ByAudience(machine=num_bytes, human=format_capacity(num_bytes))


def _address_cell(address: int) -> ByAudience:
    """A 32-bit Acorn address as an audience-aware cell.

    Humans read the conventional ``0x``-prefixed 8-hex-digit form;
    machine formatters (JSON, TSV) get the raw integer, so a consumer
    never has to parse a base back out of a string.
    """
    return ByAudience(machine=address, human=f"0x{address:08X}")


def _kv_table(title: str, pairs: list[tuple[str, str, object]]):
    """Build a transposed single-row table from (key, label, value) tuples.

    Each tuple becomes a column whose sole row holds the value. A value
    may be a plain string, an integer (for machine-readable counts), or
    a :class:`~asyoulikeit.ByAudience` cell that renders one way for
    humans and another for machine formatters. Transposed presentation
    turns the one-row table into a key-value report in the display
    formatter.
    """
    from asyoulikeit.tabular_data import TableContent

    tc = TableContent(title=title, present_transposed=True)
    row: dict = {}
    for i, (key, label, value) in enumerate(pairs):
        tc.add_column(key, label, header=(i == 0))
        row[key] = value
    tc.add_row(**row)
    return tc


@cli.command()
@click.argument("file_spec")
def cat(file_spec: str) -> None:
    """Dump file contents to stdout as raw bytes.

    Accepts a ``FILE_SPEC``.

    Use :command:`disc type` for Acorn text files — this command
    writes bytes verbatim, so files using Acorn ``\\r`` line endings
    will render unreadably on a Unix terminal.
    """
    _image, path = parse_file_spec(file_spec)
    if not path:
        raise click.UsageError("PATH is required")
    resolved = resolve_mount(file_spec)
    mount = resolved.mount
    target = resolved.path or mount.path_root()
    if not mount.exists(target):
        raise FSError(f"path not found: {target}", exit_code=ExitCode.OS_FILE)
    if mount.stat(target).is_dir:
        raise FSError(f"'{target}' is a directory", exit_code=ExitCode.OS_FILE)
    sys.stdout.buffer.write(mount.read_bytes(target))


# ---------------------------------------------------------------------------
# type — display a text file with line-ending translation
# ---------------------------------------------------------------------------

_LINE_ENDING_PATTERN = re.compile(rb"\r\n|\r|\n")
_LINE_ENDING_TARGETS: dict[str, bytes] = {
    "lf": b"\n",
    "crlf": b"\r\n",
    "cr": b"\r",
}


def _translate_line_endings(data: bytes, mode: str) -> bytes:
    """Rewrite any of ``\\r\\n``, ``\\r``, ``\\n`` in *data* to the *mode* target.

    ``mode`` is ``"host"``, ``"lf"``, ``"crlf"``, ``"cr"``, or
    ``"keep"``.  ``"host"`` resolves to ``\\r\\n`` on Windows and
    ``\\n`` elsewhere.  ``"keep"`` returns the data unchanged.
    """
    if mode == "keep":
        return data
    if mode == "host":
        target = b"\r\n" if os.name == "nt" else b"\n"
    else:
        target = _LINE_ENDING_TARGETS[mode]
    return _LINE_ENDING_PATTERN.sub(target, data)


@cli.command(name="type")
@click.argument("file_spec")
@click.option(
    "--line-endings",
    "-l",
    type=click.Choice(["host", "lf", "crlf", "cr", "keep"], case_sensitive=False),
    default="host",
    show_default=True,
    help=(
        "Translate line endings to: host = LF on macOS/Linux, CRLF on Windows; "
        "lf/crlf/cr = force a specific style; keep = no translation."
    ),
)
def type_(file_spec: str, line_endings: str) -> None:
    """Display a text file with line endings translated for the host.

    Accepts a ``FILE_SPEC``.

    Acorn text files terminate lines with ``\\r`` (carriage return).
    Dumped raw to a Unix terminal each line overwrites the previous,
    so the file appears blank.  This command translates ``\\r``,
    ``\\n`` and ``\\r\\n`` to the host's native line ending by
    default; override with ``--line-endings``.

    Acorn alias: *TYPE.
    """
    _image, path = parse_file_spec(file_spec)
    if not path:
        raise click.UsageError("PATH is required")
    resolved = resolve_mount(file_spec)
    mount = resolved.mount
    target = resolved.path or mount.path_root()
    if not mount.exists(target):
        raise FSError(f"path not found: {target}", exit_code=ExitCode.OS_FILE)
    if mount.stat(target).is_dir:
        raise FSError(f"'{target}' is a directory", exit_code=ExitCode.OS_FILE)
    data = _translate_line_endings(mount.read_bytes(target), line_endings.lower())
    sys.stdout.buffer.write(data)


_alias("*TYPE", "type")


@cli.command()
@click.argument("file_spec")
@report_output(reports={"matches": "Paths matching the wildcard pattern."})
def find(file_spec: str):
    """Find files matching an Acorn wildcard pattern.

    Accepts an ``IMAGE_SPEC`` (lists every file) or a ``FILE_SPEC``
    whose ``PATH_SPEC`` is the wildcard pattern.

    Accepts the same ``adfs:`` / ``afs:`` / ``dfs:`` prefixes as
    every other command to scope the search to a single partition.
    Without a prefix, partitioned hard-disc images (ADFS + AFS) are
    searched in their entirety and each result is emitted with the
    partition prefix that would feed back into a follow-up command
    unchanged.  Single-partition images emit bare paths, unchanged
    from earlier behaviour.
    """
    from asyoulikeit.tabular_data import Report, Reports, TableContent

    from .mount import split_selector

    image, pattern = parse_file_spec(file_spec)
    if not pattern:
        raise click.UsageError("PATTERN is required")
    selector, bare_pattern = split_selector(pattern)

    if selector is not None:
        # An explicit prefix scopes the search to that one partition; the
        # mount resolution validates it ("no such partition" otherwise).
        selectors = [selector]
        emit_prefix = True
    else:
        # No prefix: search every identified partition. A multi-partition
        # image labels each hit with its selector so a result feeds back
        # into a follow-up command unchanged; a single-partition image
        # keeps bare paths.
        selectors = partition_selectors(image)
        emit_prefix = len(selectors) > 1

    rows: list[dict] = []
    for sel in selectors:
        resolved = resolve_mount(f"{image}:{sel}:")
        mount = resolved.mount
        prefix = f"{sel}:" if emit_prefix else ""
        _find_recursive(mount, mount.path_root(), bare_pattern, prefix, rows)

    table = TableContent(title="matches")
    table.add_column("path", "Path", header=True)
    for row in rows:
        table.add_row(**row)
    return Reports(matches=Report(data=table))


def _match_acorn_wildcard(pattern: str, name: str) -> bool:
    """Match a name against an Acorn-style wildcard pattern.

    ``*`` matches any sequence, ``?`` matches one character.
    Case-insensitive to match Acorn convention.
    """
    import fnmatch

    # Acorn wildcards use the same semantics as fnmatch.
    return fnmatch.fnmatch(name.upper(), pattern.upper())


def _find_recursive(mount, path: str, pattern: str, prefix: str, rows: list[dict]) -> None:
    """Walk *mount* from *path*, collecting entries matching *pattern*.

    ``prefix`` is prepended to each emitted path — empty on a
    single-partition image, ``adfs:`` / ``afs:`` on a partitioned one —
    so every row is directly consumable by a follow-up command.
    """
    for child in mount.iter_entries(path):
        if _match_acorn_wildcard(pattern, child.name) or _match_acorn_wildcard(
            pattern, child.path
        ):
            rows.append({"path": f"{prefix}{child.path}"})
        if child.is_dir:
            _find_recursive(mount, child.path, pattern, prefix, rows)


@cli.command()
@click.argument("file_spec")
def freemap(file_spec: str) -> None:
    """Show the free-space map as a sector matrix.

    Accepts a ``FILE_SPEC``; a partition prefix scopes the map to that
    partition. Each cell is one sector — ``.`` free, ``█`` used — laid
    out in rows sized to the terminal.
    """
    import shutil

    from oaknut.filesystem import FreeMap

    with resolve_mount(file_spec) as resolved:
        mount = resolved.mount
        if not isinstance(mount, FreeMap):
            raise click.ClickException(f"{resolved.filesystem} provides no free-space map")
        data = mount.free_map()

    width = shutil.get_terminal_size((80, 24)).columns
    click.echo("Legend: █ = used, . = free")
    click.echo()
    for line in _render_free_map_lines(data, width):
        click.echo(line)
    click.echo()

    total_free = sum(length for _, length in data.free_regions)
    if data.free_regions:
        largest = max(length for _, length in data.free_regions)
        click.echo(
            f"Free: {total_free} of {data.total_sectors} sectors in "
            f"{len(data.free_regions)} region(s) (largest {largest} contiguous)"
        )
    else:
        click.echo(f"Free: 0 of {data.total_sectors} sectors")


def _render_free_map_lines(data, width: int) -> list[str]:
    """Render the sector matrix: one glyph per sector, rows filling *width*.

    Each row is prefixed with the sector offset at its start; ``.`` marks
    a free sector, ``█`` a used one. The layout follows the terminal
    width and carries no disc geometry.
    """
    free = bytearray(data.total_sectors)
    for start, length in data.free_regions:
        for sector in range(start, min(start + length, data.total_sectors)):
            free[sector] = 1

    label_width = max(len(str(max(data.total_sectors - 1, 0))), 4)
    cells_per_row = max(1, width - label_width - 1)
    lines: list[str] = []
    for row_start in range(0, data.total_sectors, cells_per_row):
        row_end = min(row_start + cells_per_row, data.total_sectors)
        glyphs = "".join("." if free[s] else "█" for s in range(row_start, row_end))
        lines.append(f"{row_start:>{label_width}} {glyphs}")
    return lines


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
def validate(image: Path) -> None:
    """Check disc image structure for inconsistencies.

    On a clean image, prints nothing and exits 0 — the silence-is-golden
    convention, so the command is composable with ``&&`` in shell
    pipelines and CI scripts. On a damaged image, prints one
    ``Error: <description>`` line on stderr per defect detected,
    followed by an ``N error(s) found`` summary line, and exits with
    code 65 (``EX_DATAERR``).

    DFS, ADFS floppies, and ADFS hard discs are supported. Defects
    surfaced include catalogue overflow, files extending past the end
    of the disc, two files claiming the same sector, duplicate
    filenames (DFS) and free-space-map checksum or structure problems
    (ADFS).
    """
    from oaknut.exception import render_error
    from oaknut.filesystem import Validatable

    from .console import print_error

    with resolve_mount(str(image)) as resolved:
        mount = resolved.mount
        if not isinstance(mount, Validatable):
            # A filesystem with no structural checks (AFS) is reported
            # clean rather than erroring — nothing to find.
            return
        errors = mount.validate()

    if not errors:
        return

    for err in errors:
        for line, is_continuation in render_error(err):
            print_error(line, is_continuation)
    plural = "" if len(errors) == 1 else "s"
    click.echo(f"{len(errors)} error{plural} found", err=True)
    raise SystemExit(int(ExitCode.DATA_ERR))


# ---------------------------------------------------------------------------
# File I/O commands
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("file_spec")
@click.argument("host_path", required=False, default=None)
@click.option(
    "--meta-format",
    type=click.Choice(
        [
            "inf-trad",
            "inf-pieb",
            "xattr-acorn",
            "xattr-pieb",
            "filename-riscos",
            "filename-mos",
            "none",
        ],
        case_sensitive=False,
    ),
    default="inf-trad",
    help="Metadata sidecar format.",
)
@click.option("--owner", type=int, default=0, help="Econet owner ID for PiEB formats.")
def get(
    file_spec: str,
    host_path: str | None,
    meta_format: str,
    owner: int,
) -> None:
    """Export a file from the image to the host filesystem.

    Accepts a ``FILE_SPEC`` and an optional ``HOST_PATH``.

    When ``HOST_PATH`` is omitted, the file is written to the current
    working directory under its on-disc Acorn name. When
    ``HOST_PATH`` is ``-``, the raw bytes go to stdout with no
    metadata sidecar — equivalent to :command:`disc cat`. Otherwise
    ``HOST_PATH`` is the destination path on the host.

    Acorn metadata (load address, exec address, access bits) is
    preserved alongside the data file according to ``--meta-format``.
    The default ``inf-trad`` writes a traditional ``HOST_PATH.inf``
    sidecar; ``xattr-acorn`` stashes the metadata in host extended
    attributes; ``filename-riscos``/``filename-mos`` encode it into
    the host filename; ``none`` drops it entirely. See
    :doc:`/cli/conventions/metadata` for the full mapping and
    trade-offs.
    """
    from oaknut.file import AcornMeta, MetaFormat, export_with_metadata
    from oaknut.filesystem import AcornMetadata

    _image, path = parse_file_spec(file_spec)
    if not path:
        raise click.UsageError("PATH is required")
    host_path = Path(host_path) if host_path is not None else None
    resolved = resolve_mount(file_spec)
    mount = resolved.mount
    target = resolved.path or mount.path_root()
    if not mount.exists(target):
        raise FSError(f"path not found: {target}", exit_code=ExitCode.OS_FILE)
    entry = mount.stat(target)
    if entry.is_dir:
        raise FSError(f"'{target}' is a directory", exit_code=ExitCode.OS_FILE)

    data = mount.read_bytes(target)

    # Stdout mode.
    if host_path is not None and str(host_path) == "-":
        sys.stdout.buffer.write(data)
        return

    # Acorn metadata travels with the data when the filesystem carries it.
    if isinstance(mount, AcornMetadata):
        meta = mount.acorn_meta(target)
    else:
        meta = AcornMeta(load_address=None, exec_address=None, access=0)

    if host_path is None:
        host_path = Path(entry.name)

    resolved_meta_format: MetaFormat | None
    if meta_format == "none":
        resolved_meta_format = None
    else:
        resolved_meta_format = MetaFormat(meta_format)

    export_with_metadata(
        data,
        host_path,
        meta,
        meta_format=resolved_meta_format,
        owner=owner,
        filename=entry.name,
    )


@cli.command()
@click.argument("file_spec")
@click.argument("host_path", required=False, default=None)
@click.option(
    "--load",
    "load_address",
    type=str,
    default=None,
    help="Load address; base from prefix (0x hex e.g. 0x1900, else decimal).",
)
@click.option(
    "--exec",
    "exec_address",
    type=str,
    default=None,
    help="Exec address; base from prefix (0x hex e.g. 0x8023, else decimal).",
)
@click.option(
    "--meta-format",
    type=click.Choice(
        [
            "inf-trad",
            "inf-pieb",
            "xattr-acorn",
            "xattr-pieb",
            "filename-riscos",
            "filename-mos",
            "none",
        ],
        case_sensitive=False,
    ),
    default=None,
    help="Metadata format to read from host file.",
)
def put(
    file_spec: str,
    host_path: str | None,
    load_address: str | None,
    exec_address: str | None,
    meta_format: str | None,
) -> None:
    """Import a host file into the image.

    Accepts a ``FILE_SPEC`` (the in-image destination) and a
    ``HOST_PATH``.

    ``HOST_PATH`` is required. When it is ``-``, the raw bytes are
    read from stdin with no metadata-sidecar lookup; supply
    ``--load`` / ``--exec`` to set the addresses, otherwise they
    default to ``0xFFFF`` (the Acorn "address not meaningful"
    sentinel). Otherwise ``HOST_PATH`` names the host file to
    import.

    When reading from a host file, Acorn metadata (load address,
    exec address, access bits) is sourced from the surroundings of
    the data file according to ``--meta-format``. With ``--meta-format``
    omitted, the default cascade tries — in order — a traditional
    ``HOST_PATH.inf`` sidecar, then host extended attributes, then a
    RISC-OS filename suffix, stopping at the first hit. ``--load``
    and ``--exec`` always win over what the cascade finds; their
    number base comes from the value's prefix (``0x`` for hex —
    e.g. ``0x1900`` — otherwise decimal), so a bare ``1900`` is
    decimal, not hex. See :doc:`/cli/conventions/metadata` for the
    full mapping and trade-offs.
    """
    from oaknut.file import AcornMeta, parse_address
    from oaknut.filesystem import AcornMetadata

    _image, path = parse_file_spec(file_spec)
    if not path:
        raise click.UsageError("PATH is required")
    host_path = Path(host_path) if host_path is not None else None

    # Default addresses: 0xFFFF matches the convention for text/data
    # files on DFS and ADFS where the address is not meaningful.
    _DEFAULT_ADDR = 0xFFFF

    # Read data.
    if host_path is not None and str(host_path) == "-":
        data = sys.stdin.buffer.read()
        resolved_load = parse_address(load_address) if load_address else _DEFAULT_ADDR
        resolved_exec = parse_address(exec_address) if exec_address else _DEFAULT_ADDR
    elif host_path is not None:
        # Try to import with metadata.
        from oaknut.file import DEFAULT_IMPORT_META_FORMATS, MetaFormat, import_with_metadata

        if meta_format is not None and meta_format != "none":
            meta_formats = (MetaFormat(meta_format),)
        else:
            meta_formats = DEFAULT_IMPORT_META_FORMATS

        _clean_path, _label, meta = import_with_metadata(
            host_path,
            meta_formats=meta_formats,
        )
        data = host_path.read_bytes()
        resolved_load = parse_address(load_address) if load_address else (meta.load_address or 0)
        resolved_exec = parse_address(exec_address) if exec_address else (meta.exec_address or 0)
    else:
        raise click.ClickException("HOST_PATH is required (or use - for stdin)")

    with resolve_mount(file_spec, writable=True) as resolved:
        mount = resolved.mount
        target = resolved.path or mount.path_root()
        # The generic write carries no addresses; set them after, when the
        # filesystem records Acorn metadata (DFS/ADFS/AFS), preserving the
        # access the write established.
        mount.write_bytes(target, data)
        if isinstance(mount, AcornMetadata):
            access = mount.acorn_meta(target).access
            mount.set_acorn_meta(
                target,
                AcornMeta(
                    load_address=resolved_load,
                    exec_address=resolved_exec,
                    access=access,
                ),
            )


# ---------------------------------------------------------------------------
# Modification commands
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("file_spec")
@click.argument("paths", nargs=-1)
@click.option("-f", "--force", is_flag=True, help="Ignore missing, override locks.")
@click.option("-r", "--recursive", is_flag=True, help="Remove directories recursively.")
@click.option("--dry-run", is_flag=True, help="Print what would be removed.")
def rm(
    file_spec: str,
    paths: tuple[str, ...],
    force: bool,
    recursive: bool,
    dry_run: bool,
) -> None:
    """Delete file(s) from the image (Acorn alias: *DELETE).

    Accepts a ``FILE_SPEC`` followed by zero or more bare ``PATH_SPEC``
    arguments — the first entry to delete travels in the ``FILE_SPEC``,
    additional in-image paths follow. Each path may contain Acorn
    wildcards (``*``, ``#``); ``-r`` descends into directory matches
    and removes children before the directory itself.
    """
    from .mount import split_selector

    image, first_path = parse_file_spec(file_spec)
    all_paths: tuple[str, ...] = (first_path, *paths) if first_path else paths
    if not all_paths:
        raise click.UsageError("at least one PATH is required")

    # Every path addresses the same image; the first path's selector
    # picks the partition, and the rest must agree (mv/rm are single
    # partition). Strip selectors to bare in-partition patterns.
    selector, _ = split_selector(all_paths[0])
    bare_patterns = [split_selector(p)[1] for p in all_paths]
    prefix = f"{selector}:" if selector else ""

    with resolve_mount(f"{image}:{prefix}", writable=not dry_run) as resolved:
        mount = resolved.mount
        for pattern in bare_patterns:
            # --force downgrades "no matches" to a no-op.
            try:
                targets = list(_iter_target_paths(mount, pattern, recursive=recursive))
            except click.ClickException:
                if force:
                    continue
                raise

            for target in targets:
                if mount.stat(target).is_dir and not recursive:
                    raise click.ClickException(
                        f"'{target}' is a directory (use -r to remove recursively)"
                    )
                if dry_run:
                    click.echo(f"would remove: {target}")
                    continue
                mount.remove(target, force=force)


_alias("*DELETE", "rm")


@cli.command()
@click.argument("src")
@click.argument("dst")
@click.option("-f", "--force", is_flag=True, help="Overwrite existing destination.")
def mv(src: str, dst: str, force: bool) -> None:
    """Rename or move a file within the image (Acorn alias: *RENAME).

    Accepts two ``FILE_SPEC`` arguments — source and destination, both
    of which must name the same image. mv is single-image: the library
    renames a directory entry in place and cannot move across
    filesystems.
    """
    from .mount import split_selector

    src_image, _ = parse_file_spec(src)
    dst_image, dst_in = parse_file_spec(dst)
    if src_image.resolve() != dst_image.resolve():
        raise click.UsageError(
            f"mv source and destination must name the same image; got {src_image} and {dst_image}"
        )
    _, bare_dst = split_selector(dst_in)

    with resolve_mount(src, writable=True) as resolved:
        mount = resolved.mount
        bare_src = resolved.path
        # Pre-check existence so the "path not found" diagnostic carries
        # the user's original input rather than a library-internal leaf.
        if not mount.exists(bare_src):
            raise FSError(f"path not found: {bare_src}", exit_code=ExitCode.OS_FILE)
        mount.rename(bare_src, bare_dst)


_alias("*RENAME", "mv")


@cli.command()
@click.argument("src")
@click.argument("dst")
@click.option("-f", "--force", is_flag=True, help="Overwrite existing destination.")
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    help="Copy directories recursively.",
)
def cp(src: str, dst: str, force: bool, recursive: bool) -> None:
    """Copy file(s) or a tree within or between disc images.

    Acorn alias: *COPY.

    Accepts two ``FILE_SPEC`` arguments — source and destination.
    Cross-image copies are the normal case; for an in-image copy,
    name the same image on both sides
    (``disc cp image.adl:$.Original image.adl:$.Copy``).

    Source paths may contain Acorn wildcards (``*`` = any sequence,
    ``#`` = any single character); when a wildcard expands to multiple
    matches the destination must denote a directory — either trailing
    ``/`` or an existing directory.  ``-r``/``--recursive`` copies a
    directory and everything under it, creating intermediate
    destination directories as needed.  Copies across DFS, ADFS, and
    AFS in any combination; load/exec addresses are preserved and
    access attributes are mapped best-effort (DFS only has the locked
    bit).
    """
    _cp_dispatch(src, dst, force=force, recursive=recursive)


# ---------------------------------------------------------------------------
# cp orchestration
# ---------------------------------------------------------------------------


_WILDCARD_CHARS = ("*", "?", "#")


def _has_wildcard(path: str) -> bool:
    return any(ch in path for ch in _WILDCARD_CHARS)


def _acorn_to_fnmatch(pattern: str) -> str:
    """Translate Acorn wildcards (``#``) to fnmatch syntax."""
    return pattern.replace("#", "?")


def _match_acorn(pattern: str, name: str) -> bool:
    import fnmatch

    return fnmatch.fnmatch(name.upper(), _acorn_to_fnmatch(pattern.upper()))


def _split_parent_leaf(bare: str) -> tuple[str, str]:
    """Split a path at its last ``.`` into ``(parent, leaf)``."""
    if "." in bare:
        return bare.rsplit(".", 1)
    return "", bare


def _dst_ends_slash(bare: str) -> tuple[str, bool]:
    """Strip a trailing ``/`` from ``bare`` and report whether one was present."""
    if bare.endswith("/") and bare != "/":
        return bare[:-1], True
    return bare, False


def _expand_target_paths(mount, pattern: str) -> list[str]:
    """Resolve *pattern* to a list of existing in-partition path strings.

    A literal path resolves to a one-element list; an Acorn wildcard on
    the *leaf* component expands against the parent directory's entries
    (wildcards in directory components are unsupported). No match is an
    error. The mount-based counterpart of :func:`_expand_path_spec`.
    """
    if _has_wildcard(pattern):
        parent, leaf_pattern = _split_parent_leaf(pattern)
        if _has_wildcard(parent):
            raise click.ClickException(
                f"wildcards in directory components are not supported: {pattern!r}"
            )
        parent = parent or mount.path_root()
        if not mount.exists(parent) or not mount.stat(parent).is_dir:
            raise click.ClickException(
                f"parent directory of glob does not exist: {parent or '$'!r}"
            )
        matches = [
            e.path for e in mount.iter_entries(parent) if _match_acorn(leaf_pattern, e.name)
        ]
        if not matches:
            raise click.ClickException(f"no matches for {pattern!r}")
        return matches
    if not mount.exists(pattern):
        raise click.ClickException(f"path not found: {pattern}")
    return [pattern]


def _walk_post_order_mount(mount, path: str):
    """Yield every descendant path of *path*, children before parents."""
    if not mount.stat(path).is_dir:
        yield path
        return
    for child in mount.iter_entries(path):
        yield from _walk_post_order_mount(mount, child.path)
    yield path


def _iter_target_paths(mount, pattern: str, *, recursive: bool):
    """Enumerate in-partition paths for a bulk-mutating command on *mount*.

    Expands wildcards on *pattern* and, when *recursive*, walks each
    directory match post-order (children before the directory). The
    mount-based counterpart of :func:`_iter_targets`.
    """
    for seed in _expand_target_paths(mount, pattern):
        if recursive and mount.stat(seed).is_dir:
            yield from _walk_post_order_mount(mount, seed)
        else:
            yield seed


def _mutate_access(file_spec: str, *, recursive: bool, dry_run: bool, verb, transform) -> None:
    """Apply an access-byte *transform* to every target of *file_spec*.

    *transform* maps the current :class:`~oaknut.file.Access` to the new
    one. Access is wire-canonical at the mount boundary — each filesystem
    maps it to its own on-disc layout (DFS keeps only the lock bit), so
    the CLI works in one representation. *verb* builds the --dry-run line.
    A flat catalogue's notional directories carry no access and are
    skipped.
    """
    from oaknut.file import Access, AcornMeta
    from oaknut.filesystem import AcornMetadata, HierarchicalDirectories

    _image, path = parse_file_spec(file_spec)
    if not path:
        raise click.UsageError("PATH is required")
    with resolve_mount(file_spec, writable=not dry_run) as resolved:
        mount = resolved.mount
        if not isinstance(mount, AcornMetadata):
            raise FSError(
                f"{resolved.filesystem} files carry no access bits",
                exit_code=ExitCode.OS_FILE,
            )
        flat = not isinstance(mount, HierarchicalDirectories)
        pattern = resolved.path or mount.path_root()
        for target in _iter_target_paths(mount, pattern, recursive=recursive):
            if flat and mount.stat(target).is_dir:
                continue  # a flat catalogue's directories are notional
            if dry_run:
                click.echo(verb(target))
                continue
            meta = mount.acorn_meta(target)
            mount.set_acorn_meta(
                target,
                AcornMeta(
                    load_address=meta.load_address,
                    exec_address=meta.exec_address,
                    access=int(transform(Access(meta.access))),
                ),
            )


def _cp_dispatch(src_spec: str, dst_spec: str, *, force: bool, recursive: bool) -> None:
    """Orchestrate a cp invocation.

    Handles single-file copy, wildcard expansion on the source,
    recursive directory copy, and their combinations, across any pair of
    filesystems. The source is opened read-only and the destination
    writable; source data is buffered into the copy plan during the read
    pass, so an in-image copy (same file both sides) reads the original
    bytes before any write.
    """
    with (
        resolve_mount(src_spec) as src_resolved,
        resolve_mount(dst_spec, writable=True) as dst_resolved,
    ):
        src_mount = src_resolved.mount
        dst_mount = dst_resolved.mount
        dst_bare, dst_slash = _dst_ends_slash(dst_resolved.path)

        items = _collect_copy_items(
            src_mount,
            src_resolved.path,
            dst_mount=dst_mount,
            dst_bare=dst_bare,
            dst_slash=dst_slash,
            recursive=recursive,
        )

        for item in items:
            if item["kind"] == "mkdir":
                _ensure_dir_chain(dst_mount, item["dst"])
            elif item["kind"] == "file":
                _write_copy_item(dst_mount, item["dst"], item, force)


def _collect_copy_items(
    src_mount,
    src_bare: str,
    *,
    dst_mount,
    dst_bare: str,
    dst_slash: bool,
    recursive: bool,
) -> list[dict]:
    """Walk the source side once, returning a plan of copy items.

    Each item is either ``{"kind": "mkdir", "dst": path}`` or
    ``{"kind": "file", "dst": path, "data": bytes, "load": int,
    "exec": int, "access": int}``. The plan is linear; the write phase
    executes items in order.
    """
    from oaknut.filesystem import HierarchicalDirectories

    items: list[dict] = []
    src_is_dfs = not isinstance(src_mount, HierarchicalDirectories)
    dst_is_dfs = not isinstance(dst_mount, HierarchicalDirectories)

    if _has_wildcard(src_bare):
        matches = _expand_glob(src_mount, src_bare)
        if not matches:
            raise click.ClickException(f"no matches for {src_bare!r}")
        dst_must_be_dir = len(matches) > 1 or any(
            src_mount.stat(m).is_dir for m in matches
        )
        _check_dst_is_dir(dst_mount, dst_bare, dst_slash, required=dst_must_be_dir)
        if dst_must_be_dir or dst_slash:
            items.append({"kind": "mkdir", "dst": dst_bare})
        for match in matches:
            entry = src_mount.stat(match)
            # DFS "$" globbed as a parent? Flatten onto dst_bare.
            transparent = src_is_dfs and entry.is_dir and entry.name == "$"
            sub_dst = dst_bare if transparent else _join(dst_bare, entry.name)
            if entry.is_dir:
                if not recursive:
                    click.echo(
                        f"skipping directory {match} (use -r to copy recursively)",
                        err=True,
                    )
                    continue
                _walk_tree(src_mount, match, sub_dst, items, src_is_dfs=src_is_dfs)
            else:
                items.append(_file_item(src_mount, match, sub_dst))
        if dst_is_dfs:
            _validate_dfs_items(items)
        return items

    # Non-glob: single source.
    if not src_mount.exists(src_bare):
        raise click.ClickException(f"path not found: {src_bare}")
    source = src_mount.stat(src_bare)

    # Figure out whether the destination should be treated as a target
    # directory (copy source "into" it) or as the full target path.
    dst_is_dir_like = dst_slash or _path_is_existing_dir(dst_mount, dst_bare)

    if source.is_dir:
        if not recursive:
            raise click.ClickException(f"'{src_bare}' is a directory (use -r to copy recursively)")
        # A source that IS the root (ADFS/AFS ``$``, or the DFS virtual
        # root whose children are directory letters) is transparent —
        # there's no sensible subdirectory to wrap it in; its contents
        # land at dst_bare directly. The DFS ``$`` directory behaves the
        # same (it maps one-for-one onto ADFS ``$``, issue #6).
        transparent = source.name in ("", "$")
        if transparent:
            rel = dst_bare
            items.append({"kind": "mkdir", "dst": dst_bare})
        elif dst_is_dir_like:
            rel = _join(dst_bare, source.name)
            items.append({"kind": "mkdir", "dst": dst_bare})
            items.append({"kind": "mkdir", "dst": rel})
        else:
            rel = dst_bare
            items.append({"kind": "mkdir", "dst": rel})
        _walk_tree(src_mount, src_bare, rel, items, src_is_dfs=src_is_dfs)
        if dst_is_dfs:
            _validate_dfs_items(items)
        return items

    # Source is a file.
    if dst_is_dir_like:
        items.append({"kind": "mkdir", "dst": dst_bare})
        rel = _join(dst_bare, source.name)
    else:
        rel = dst_bare
    items.append(_file_item(src_mount, src_bare, rel))
    if dst_is_dfs:
        _validate_dfs_items(items)
    return items


def _expand_glob(src_mount, src_bare: str) -> list[str]:
    """Paths of children of the literal parent matching the leaf pattern.

    Only the leaf component of ``src_bare`` may contain wildcards; the
    parent directory path is navigated literally.
    """
    parent, leaf_pattern = _split_parent_leaf(src_bare)
    if _has_wildcard(parent):
        raise click.ClickException(
            f"wildcards in directory components are not supported: {src_bare!r}"
        )
    parent = parent or src_mount.path_root()
    if not src_mount.exists(parent) or not src_mount.stat(parent).is_dir:
        raise click.ClickException(f"parent directory of glob does not exist: {parent or '$'!r}")
    return [e.path for e in src_mount.iter_entries(parent) if _match_acorn(leaf_pattern, e.name)]


def _map_dst_path_for_dfs(path: str) -> str:
    """Map an ADFS-style absolute path to a DFS path.

    ``$.F`` stays as ``$.F``.  ``$.D.F`` maps to ``D.F`` — the single
    ADFS subdirectory level flattens onto DFS's single-letter directory
    prefix.  Anything deeper, or with a multi-character subdirectory
    name, can't be represented on DFS and raises.
    """
    if path == "$":
        return "$"
    if path.startswith("$."):
        rest = path[2:]
    else:
        rest = path
    dot_count = rest.count(".")
    if dot_count == 0:
        # "$.F" → rest="F", the file in $ directory; DFS is "$.F".
        return f"$.{rest}"
    if dot_count == 1:
        dir_part, file_part = rest.split(".")
        if len(dir_part) != 1:
            raise click.ClickException(
                f"cannot map {path!r} to DFS: directory name "
                f"{dir_part!r} is longer than one character"
            )
        return f"{dir_part}.{file_part}"
    raise click.ClickException(
        f"cannot map {path!r} to DFS: path is nested deeper than "
        "DFS's single directory-letter model allows"
    )


def _remap_items_for_dfs(items: list[dict]) -> list[dict]:
    """Rewrite a copy plan for a DFS destination.

    Drops ``mkdir`` items (DFS has no filesystem-level directory
    objects to create) and rewrites each file's dst path to DFS
    form via :func:`_map_dst_path_for_dfs`, which raises on any
    path that can't be represented on DFS.
    """
    out: list[dict] = []
    for item in items:
        if item["kind"] == "mkdir":
            # Validate but don't materialise — a mkdir at an
            # unrepresentable path still indicates the source tree
            # is too deep for DFS, so let the mapper raise on it.
            _map_dst_path_for_dfs(item["dst"])
            continue
        new = dict(item)
        new["dst"] = _map_dst_path_for_dfs(item["dst"])
        out.append(new)
    return out


def _validate_dfs_items(items: list[dict]) -> None:
    """Mutate ``items`` in place, remapping/dropping for DFS."""
    items[:] = _remap_items_for_dfs(items)


def _walk_tree(
    src_mount, dir_path: str, dst_prefix: str, items: list[dict], *, src_is_dfs: bool
) -> None:
    """Depth-first walk of *dir_path*: a mkdir item per directory, a file
    item per file.

    When the source is DFS, a child directory named ``$`` is transparent
    — its contents land at ``dst_prefix`` rather than under a ``$``
    subdirectory — so the DFS default directory collapses onto the
    destination root in a DFS → ADFS/AFS copy. DFS's other letters become
    subdirectories as usual.
    """
    for child in src_mount.iter_entries(dir_path):
        if src_is_dfs and child.is_dir and child.name == "$":
            _walk_tree(src_mount, child.path, dst_prefix, items, src_is_dfs=src_is_dfs)
            continue
        rel = _join(dst_prefix, child.name)
        if child.is_dir:
            items.append({"kind": "mkdir", "dst": rel})
            _walk_tree(src_mount, child.path, rel, items, src_is_dfs=src_is_dfs)
        else:
            items.append(_file_item(src_mount, child.path, rel))


def _file_item(src_mount, src_path: str, rel_dst: str) -> dict:
    """Build a ``file`` copy item, reading data and metadata from the mount."""
    from oaknut.filesystem import AcornMetadata

    load = exec_addr = access = 0
    if isinstance(src_mount, AcornMetadata):
        meta = src_mount.acorn_meta(src_path)
        load = meta.load_address or 0
        exec_addr = meta.exec_address or 0
        access = int(meta.access)
    return {
        "kind": "file",
        "dst": rel_dst,
        "data": src_mount.read_bytes(src_path),
        "load": load,
        "exec": exec_addr,
        "access": access,
    }


def _join(parent: str, leaf: str) -> str:
    if not parent or parent == "$":
        return f"$.{leaf}" if parent == "$" else leaf
    return f"{parent}.{leaf}"


def _path_is_existing_dir(mount, bare: str) -> bool:
    """Is *bare* an existing directory on the destination mount?"""
    return mount.exists(bare) and mount.stat(bare).is_dir


def _check_dst_is_dir(mount, bare: str, slash: bool, *, required: bool) -> None:
    """Enforce the "destination must be a directory" rule."""
    if slash:
        return
    if _path_is_existing_dir(mount, bare):
        return
    if required:
        raise click.ClickException(
            f"destination {bare!r} must be a directory "
            "(end with '/' or pre-create it) when the source expands "
            "to multiple items or contains directories"
        )


def _ensure_dir_chain(dst_mount, bare: str) -> None:
    """Create *bare* and any missing parents on the destination.

    A flat catalogue (DFS) has no true subdirectories to create — the
    call is a no-op there; a write later registers the directory letter
    implicitly.
    """
    from oaknut.filesystem import HierarchicalDirectories

    if not isinstance(dst_mount, HierarchicalDirectories):
        return
    if not bare or bare == "$":
        return
    dst_mount.make_directory(bare, parents=True, exist_ok=True)


def _write_copy_item(dst_mount, dst_path: str, item: dict, force: bool) -> None:
    """Write a file item to its destination path."""
    from oaknut.file import AcornMeta
    from oaknut.filesystem import AcornMetadata, HierarchicalDirectories

    # Ensure the parent exists for hierarchical destinations; on a flat
    # catalogue the letter prefix appears when a file claims it (and the
    # collect stage has already validated the path against DFS's shape).
    parent, _leaf = _split_parent_leaf(dst_path)
    if parent and isinstance(dst_mount, HierarchicalDirectories):
        _ensure_dir_chain(dst_mount, parent)

    if dst_mount.exists(dst_path):
        if not force:
            raise click.ClickException(f"'{dst_path}' already exists (use -f to overwrite)")
        dst_mount.remove(dst_path, force=True)

    dst_mount.write_bytes(dst_path, item["data"])
    if isinstance(dst_mount, AcornMetadata):
        dst_mount.set_acorn_meta(
            dst_path,
            AcornMeta(load_address=item["load"], exec_address=item["exec"], access=item["access"]),
        )


_alias("*COPY", "cp")


@cli.command()
@click.argument("file_spec")
@click.option(
    "-p",
    is_flag=True,
    help="Create missing parents and do not error if the directory already exists.",
)
@click.option(
    "--title",
    "dir_title",
    default=None,
    help="Set the new directory's title (ADFS only; DFS/AFS directories have none).",
)
def mkdir(file_spec: str, p: bool, dir_title: str | None) -> None:
    """Create a directory (ADFS/AFS only). Alias: *CDIR.

    Accepts a ``FILE_SPEC``. ``--title`` additionally sets the new
    directory's title, which only ADFS supports — passing it for an
    AFS directory is an error (DFS has no directories at all).
    """
    from oaknut.filesystem import HierarchicalDirectories

    _image, path = parse_file_spec(file_spec)
    if not path:
        raise click.UsageError("PATH is required")
    with resolve_mount(file_spec, writable=True) as resolved:
        mount = resolved.mount
        # mkdir is available when the filesystem nests directories; a flat
        # catalogue (DFS) does not advertise the capability.
        if not isinstance(mount, HierarchicalDirectories):
            raise click.ClickException(
                f"mkdir is not supported for {resolved.filesystem} images"
            )
        target = resolved.path or mount.path_root()
        mount.make_directory(target, parents=p, exist_ok=p, title=dir_title)


_alias("*CDIR", "mkdir")


@cli.command()
@click.argument("file_spec")
@click.argument("access")
@click.option("-r", "--recursive", is_flag=True, help="Recurse into directory matches.")
@click.option(
    "--dry-run", is_flag=True, help="Print what would change without modifying the image."
)
def chmod(
    file_spec: str,
    access: str,
    recursive: bool,
    dry_run: bool,
) -> None:
    """Set file access permissions (Acorn alias: *ACCESS).

    Accepts a ``FILE_SPEC`` and an ``ACCESS``.

    ACCESS is symbolic (e.g. LWR/R, WR/WR) or hex (0x0B, 33).
    DFS only supports the L (locked) bit; other flags are ignored.

    PATH may contain Acorn wildcards (``*``, ``#``) to apply the
    same access to every matching file.  ``-r`` recurses into any
    directory match.
    """
    from oaknut.file import parse_access

    flags = parse_access(access)
    # chmod replaces the access wholesale; the mount maps it to its layout
    # (DFS keeps only the lock bit, ADFS/AFS the full set).
    _mutate_access(
        file_spec,
        recursive=recursive,
        dry_run=dry_run,
        verb=lambda target: f"would chmod {target} {access}",
        transform=lambda _current: flags,
    )


_alias("*ACCESS", "chmod")


@cli.command()
@click.argument("file_spec")
@click.option("-r", "--recursive", is_flag=True, help="Recurse into directory matches.")
@click.option(
    "--dry-run", is_flag=True, help="Print what would change without modifying the image."
)
def lock(file_spec: str, recursive: bool, dry_run: bool) -> None:
    """Lock a file.

    Accepts a ``FILE_SPEC``.
    PATH may be a wildcard; ``-r`` recurses.
    """
    from oaknut.file import Access

    _mutate_access(
        file_spec,
        recursive=recursive,
        dry_run=dry_run,
        verb=lambda target: f"would lock {target}",
        transform=lambda current: current | Access.L,
    )


@cli.command()
@click.argument("file_spec")
@click.option("-r", "--recursive", is_flag=True, help="Recurse into directory matches.")
@click.option(
    "--dry-run", is_flag=True, help="Print what would change without modifying the image."
)
def unlock(file_spec: str, recursive: bool, dry_run: bool) -> None:
    """Unlock a file.

    Accepts a ``FILE_SPEC``.
    PATH may be a wildcard; ``-r`` recurses.
    """
    from oaknut.file import Access

    _mutate_access(
        file_spec,
        recursive=recursive,
        dry_run=dry_run,
        verb=lambda target: f"would unlock {target}",
        transform=lambda current: current & ~Access.L,
    )


@cli.command(name="set-load")
@click.argument("file_spec")
@click.argument("addr")
@click.option("-r", "--recursive", is_flag=True, help="Recurse into directory matches.")
@click.option(
    "--dry-run", is_flag=True, help="Print what would change without modifying the image."
)
def set_load(
    file_spec: str,
    addr: str,
    recursive: bool,
    dry_run: bool,
) -> None:
    """Set a file's load address.

    Accepts a ``FILE_SPEC`` and an ``ADDR``.

    ``ADDR``'s number base comes from its prefix: ``0x`` for hex
    (the usual form for Acorn addresses — e.g. ``0x1900``), ``0o``
    for octal, ``0b`` for binary, or no prefix for decimal. A bare
    ``1900`` is therefore decimal, *not* hex; write ``0x1900`` for
    the hex value. The Acorn ``&1900`` notation is not accepted.

    PATH may contain Acorn wildcards; ``-r`` recurses into directory
    matches (directories themselves are skipped — they have no load
    address field).
    """
    from oaknut.file import AcornMeta, parse_address
    from oaknut.filesystem import AcornMetadata

    _image, path = parse_file_spec(file_spec)
    if not path:
        raise click.UsageError("PATH is required")
    address = parse_address(addr)
    with resolve_mount(file_spec, writable=not dry_run) as resolved:
        mount = resolved.mount
        if not isinstance(mount, AcornMetadata):
            raise FSError(
                f"{resolved.filesystem} files carry no load address",
                exit_code=ExitCode.OS_FILE,
            )
        target_pattern = resolved.path or mount.path_root()
        for target in _iter_target_paths(mount, target_pattern, recursive=recursive):
            if mount.stat(target).is_dir:
                continue  # load address is meaningless for a directory
            if dry_run:
                click.echo(f"would set-load {target} {address:#010x}")
                continue
            meta = mount.acorn_meta(target)
            mount.set_acorn_meta(
                target,
                AcornMeta(
                    load_address=address,
                    exec_address=meta.exec_address,
                    access=meta.access,
                ),
            )


@cli.command(name="set-exec")
@click.argument("file_spec")
@click.argument("addr")
@click.option("-r", "--recursive", is_flag=True, help="Recurse into directory matches.")
@click.option(
    "--dry-run", is_flag=True, help="Print what would change without modifying the image."
)
def set_exec(
    file_spec: str,
    addr: str,
    recursive: bool,
    dry_run: bool,
) -> None:
    """Set a file's exec address.

    Accepts a ``FILE_SPEC`` and an ``ADDR``.

    ``ADDR``'s number base comes from its prefix: ``0x`` for hex
    (the usual form for Acorn addresses — e.g. ``0x8023``), ``0o``
    for octal, ``0b`` for binary, or no prefix for decimal. A bare
    ``8023`` is therefore decimal, *not* hex; write ``0x8023`` for
    the hex value. The Acorn ``&8023`` notation is not accepted.

    PATH may contain Acorn wildcards; ``-r`` recurses into directory
    matches (directories themselves are skipped — they have no exec
    address field).
    """
    from oaknut.file import AcornMeta, parse_address
    from oaknut.filesystem import AcornMetadata

    _image, path = parse_file_spec(file_spec)
    if not path:
        raise click.UsageError("PATH is required")
    address = parse_address(addr)
    with resolve_mount(file_spec, writable=not dry_run) as resolved:
        mount = resolved.mount
        if not isinstance(mount, AcornMetadata):
            raise FSError(
                f"{resolved.filesystem} files carry no exec address",
                exit_code=ExitCode.OS_FILE,
            )
        target_pattern = resolved.path or mount.path_root()
        for target in _iter_target_paths(mount, target_pattern, recursive=recursive):
            if mount.stat(target).is_dir:
                continue
            if dry_run:
                click.echo(f"would set-exec {target} {address:#010x}")
                continue
            meta = mount.acorn_meta(target)
            mount.set_acorn_meta(
                target,
                AcornMeta(
                    load_address=meta.load_address,
                    exec_address=address,
                    access=meta.access,
                ),
            )


def _require_acorn_meta(file_spec: str):
    """Resolve *file_spec* to an existing file and return its Acorn metadata.

    Raises if the path is missing, is a directory, or the filesystem does
    not carry Acorn metadata (the capability the get-load/get-exec
    commands gate on).
    """
    from oaknut.filesystem import AcornMetadata

    _image, path = parse_file_spec(file_spec)
    if not path:
        raise click.UsageError("PATH is required")
    resolved = resolve_mount(file_spec)
    mount = resolved.mount
    target = resolved.path or mount.path_root()
    if not mount.exists(target):
        raise FSError(f"path not found: {target}", exit_code=ExitCode.OS_FILE)
    if not isinstance(mount, AcornMetadata):
        raise FSError(
            f"{resolved.filesystem} files carry no load/exec address",
            exit_code=ExitCode.OS_FILE,
        )
    return mount.acorn_meta(target)


@cli.command(name="get-load")
@click.argument("file_spec")
@report_output(
    reports={
        "load": (
            "File load address: a ``0x``-prefixed 8-hex-digit string for "
            "humans, a raw integer for machine formatters."
        )
    }
)
def get_load(file_spec: str):
    """Print a file's load address.

    Accepts a ``FILE_SPEC``.
    """
    from asyoulikeit.scalar_data import ScalarContent
    from asyoulikeit.tabular_data import Report, Reports

    meta = _require_acorn_meta(file_spec)
    return Reports(
        load=Report(
            data=ScalarContent(value=_address_cell(meta.load_address), title="Load"),
        ),
    )


@cli.command(name="get-exec")
@click.argument("file_spec")
@report_output(
    reports={
        "exec": (
            "File exec address: a ``0x``-prefixed 8-hex-digit string for "
            "humans, a raw integer for machine formatters."
        )
    }
)
def get_exec(file_spec: str):
    """Print a file's exec address.

    Accepts a ``FILE_SPEC``.
    """
    from asyoulikeit.scalar_data import ScalarContent
    from asyoulikeit.tabular_data import Report, Reports

    meta = _require_acorn_meta(file_spec)
    return Reports(
        exec=Report(
            data=ScalarContent(value=_address_cell(meta.exec_address), title="Exec"),
        ),
    )


@cli.command()
@click.argument("file_spec")
@click.argument("new_title", required=False, default=None)
@report_output(reports={"title": "Current title (when no new title is supplied)."})
def title(file_spec: str, new_title: str | None):
    """Read or set a disc or directory title (Acorn alias: *TITLE).

    Accepts a ``FILE_SPEC``. With no in-image path it reads or sets
    the disc-level title (the DFS disc title, the ADFS root title, or
    the AFS partition's disc name). With a directory path it reads or
    sets that directory's title — an ADFS-only capability, since DFS
    and AFS directories have no title field. Targeting a DFS or AFS
    directory fails with a "no title" error.
    """
    from asyoulikeit.scalar_data import ScalarContent
    from asyoulikeit.tabular_data import Report, Reports
    from oaknut.file import TitleNotSupportedError
    from oaknut.filesystem import DirectoryTitled, Titled

    _image, _path = parse_file_spec(file_spec)
    with resolve_mount(file_spec, writable=new_title is not None) as resolved:
        mount = resolved.mount
        bare = resolved.path
        # No in-image path → the disc/partition title (every filesystem
        # is Titled). A path → that directory's title, which only an
        # ADFS-style DirectoryTitled filesystem carries.
        if bare:
            if not isinstance(mount, DirectoryTitled):
                raise TitleNotSupportedError(
                    f"'{bare}' cannot have a title: only ADFS directories carry one"
                )
            if new_title is None:
                current = mount.directory_title(bare)
            else:
                mount.set_directory_title(bare, new_title)
                current = None
        else:
            if not isinstance(mount, Titled):
                raise click.ClickException(
                    f"{resolved.filesystem} images carry no disc title"
                )
            if new_title is None:
                current = mount.title
            else:
                mount.set_title(new_title)
                current = None

    if current is None:
        return None
    return Reports(title=Report(data=ScalarContent(value=current, title="Title")))


_alias("*TITLE", "title")


class BootOptionParam(click.ParamType):
    """Click parameter type that accepts boot option as int (0-3) or name."""

    name = "option"

    def convert(self, value, param, ctx):
        from oaknut.file import BootOption

        if isinstance(value, int):
            if value not in range(4):
                self.fail(f"{value} is not a valid boot option (0-3)", param, ctx)
            return value

        # Try as integer string first
        try:
            iv = int(value)
            if iv not in range(4):
                self.fail(f"{iv} is not a valid boot option (0-3)", param, ctx)
            return iv
        except ValueError:
            pass

        # Try as name (case-insensitive)
        upper = value.upper()
        try:
            return BootOption[upper].value
        except KeyError:
            names = ", ".join(bo.name for bo in BootOption)
            self.fail(
                f"{value!r} is not a valid boot option (0-3 or {names})",
                param,
                ctx,
            )


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("boot_option", required=False, default=None, type=BootOptionParam())
@report_output(
    reports={
        "boot_option": (
            "Current boot option (0/OFF, 1/LOAD, 2/RUN, 3/EXEC) when no value is supplied."
        )
    }
)
def opt(image: Path, boot_option: int | None):
    """Read or set boot option (Acorn alias: *OPT4).

    Omit BOOT_OPTION to report the current setting.

    \b
    Values:
      0 / OFF   No action
      1 / LOAD  *LOAD $.!BOOT
      2 / RUN   *RUN $.!BOOT
      3 / EXEC  *EXEC $.!BOOT
    """
    from asyoulikeit.scalar_data import ScalarContent
    from asyoulikeit.tabular_data import Report, Reports
    from oaknut.filesystem import Bootable

    with resolve_mount(str(image), writable=boot_option is not None) as resolved:
        mount = resolved.mount
        if not isinstance(mount, Bootable):
            raise click.ClickException(
                f"{resolved.filesystem} images carry no boot option"
            )
        if boot_option is None:
            bo = mount.boot_option
            return Reports(
                boot_option=Report(
                    data=ScalarContent(
                        value=f"{bo.value} ({bo.name})",
                        title="Boot option",
                    ),
                ),
            )
        mount.set_boot_option(boot_option)
    return None


_alias("*OPT4", "opt")


# ---------------------------------------------------------------------------
# Whole-image operations
# ---------------------------------------------------------------------------


# Sentinel for "an ADFS hard disc", whose size comes from --capacity
# rather than a fixed-geometry format constant.
@cli.command()
@click.argument("host_path", type=click.Path(path_type=Path))
@click.option(
    "--filesystem",
    "filesystem_name",
    default=None,
    help=(
        "Filesystem to create. Inferred from the filename extension when "
        "omitted (.ssd/.dsd → acorn-dfs; .ads/.adm/.adl/.adf/.dat → adfs). "
        "Name a filesystem to override (e.g. watford-dfs)."
    ),
)
@click.option(
    "--geometry",
    "geometry_spec",
    default=None,
    help=(
        "Physical geometry. Inferred from the extension when omitted; an "
        "ambiguous (.adf) or open-ended (.dat hard disc) extension needs "
        "it. A preset (e.g. l, 80t-ds) or parameterised form "
        "(capacity=10MB, cylinders=296,heads=4,spt=33)."
    ),
)
@click.option("--title", "disc_title", default="", help="Disc title.")
def create(
    host_path: Path,
    filesystem_name: str | None,
    geometry_spec: str | None,
    disc_title: str,
) -> None:
    """Create a new empty disc image.

    The filesystem and geometry are inferred from HOST_PATH's extension —
    ``.ssd`` → Acorn DFS 80T single-sided, ``.adl`` → ADFS-L, and so on —
    with ``--filesystem`` and ``--geometry`` to override. An ambiguous
    extension (``.adf``: ADFS-S or -M?) or an open-ended one (``.dat``: a
    hard disc) has no default geometry and requires ``--geometry``.
    """
    from oaknut.filesystem import create_filesystem, creating_filesystem, filesystem_names

    suffix = host_path.suffix.lower()
    name = filesystem_name or creating_filesystem(suffix)
    if name is None:
        installed = ", ".join(sorted(filesystem_names())) or "(none)"
        raise click.ClickException(
            f"cannot infer a filesystem to create from extension {suffix!r}; "
            f"pass --filesystem (installed: {installed})"
        )

    filesystem = create_filesystem(name)
    grammar = filesystem.geometry_grammar()
    if geometry_spec is not None:
        geometry = grammar.parse(geometry_spec)
    else:
        geometry = filesystem.default_geometry(suffix)
    if geometry is None:
        presets = ", ".join(grammar.preset_names()) or "none"
        raise click.ClickException(
            f"{name} has no default geometry for {suffix!r}; pass --geometry "
            f"(presets: {presets}; or e.g. capacity=10MB)"
        )

    filesystem.create(host_path, geometry, title=disc_title)


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
def compact(image: Path) -> None:
    """Defragment a disc image, consolidating free space."""
    from oaknut.filesystem import Compactable

    with resolve_mount(str(image), writable=True) as resolved:
        mount = resolved.mount
        if not isinstance(mount, Compactable):
            raise click.ClickException(
                f"{resolved.filesystem} images cannot be compacted"
            )
        mount.compact()


# ---------------------------------------------------------------------------
# Bulk export / import
# ---------------------------------------------------------------------------


@cli.command(name="export")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("host_dir", type=click.Path(path_type=Path))
@click.option(
    "--meta-format",
    type=click.Choice(
        [
            "inf-trad",
            "inf-pieb",
            "xattr-acorn",
            "xattr-pieb",
            "filename-riscos",
            "filename-mos",
            "none",
        ],
        case_sensitive=False,
    ),
    default="inf-trad",
    help="Metadata sidecar format.",
)
@click.option("--owner", type=int, default=0, help="Econet owner ID for PiEB formats.")
@click.option("-v", "--verbose", is_flag=True, help="Show extraction progress.")
def export_cmd(image: Path, host_dir: Path, meta_format: str, owner: int, verbose: bool) -> None:
    """Bulk-export entire image to a host directory."""
    from oaknut.file import MetaFormat

    resolved_meta_format: MetaFormat | None
    if meta_format == "none":
        resolved_meta_format = None
    else:
        resolved_meta_format = MetaFormat(meta_format)

    host_dir.mkdir(parents=True, exist_ok=True)

    resolved = resolve_mount(str(image))
    mount = resolved.mount
    _export_recursive(
        mount, mount.path_root(), host_dir, resolved_meta_format, owner, verbose
    )


def _export_recursive(
    mount,
    path: str,
    host_dir: Path,
    meta_format,
    owner: int,
    verbose: bool,
) -> None:
    """Recursively export files under *path* in *mount* to the host directory."""
    from oaknut.file import AcornMeta, export_with_metadata
    from oaknut.filesystem import AcornMetadata

    for child in mount.iter_entries(path):
        if child.is_dir:
            sub_dir = host_dir / child.name
            sub_dir.mkdir(exist_ok=True)
            _export_recursive(mount, child.path, sub_dir, meta_format, owner, verbose)
        else:
            data = mount.read_bytes(child.path)
            if isinstance(mount, AcornMetadata):
                meta = mount.acorn_meta(child.path)
            else:
                meta = AcornMeta(load_address=None, exec_address=None, access=0)
            export_with_metadata(
                data,
                host_dir / child.name,
                meta,
                meta_format=meta_format,
                owner=owner,
                filename=child.name,
            )
            if verbose:
                click.echo(child.name, err=True)


@cli.command(name="import")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("host_dir", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--meta-format",
    type=click.Choice(
        [
            "inf-trad",
            "inf-pieb",
            "xattr-acorn",
            "xattr-pieb",
            "filename-riscos",
            "filename-mos",
            "none",
        ],
        case_sensitive=False,
    ),
    default=None,
    help="Metadata format to read from host files.",
)
@click.option("-v", "--verbose", is_flag=True, help="Show import progress.")
def import_cmd(
    image: Path,
    host_dir: Path,
    meta_format: str | None,
    verbose: bool,
) -> None:
    """Bulk-import a host directory into the image."""
    from oaknut.file import DEFAULT_IMPORT_META_FORMATS, MetaFormat

    if meta_format is not None and meta_format != "none":
        meta_formats = (MetaFormat(meta_format),)
    else:
        meta_formats = DEFAULT_IMPORT_META_FORMATS

    with resolve_mount(str(image), writable=True) as resolved:
        mount = resolved.mount
        _import_host_dir(mount, mount.path_root(), host_dir, meta_formats, verbose)


def _import_host_dir(mount, parent_path: str, host_dir: Path, meta_formats, verbose) -> None:
    """Recursively import a host directory into *mount* under *parent_path*."""
    from oaknut.file import AcornMeta, import_with_metadata
    from oaknut.filesystem import AcornMetadata, HierarchicalDirectories

    flat = not isinstance(mount, HierarchicalDirectories)
    for entry in sorted(host_dir.iterdir()):
        if entry.name.startswith("."):
            continue  # Skip hidden files and INF sidecars.
        if entry.suffix.lower() == ".inf":
            continue  # Skip INF sidecar files.
        if entry.is_file():
            # Derive the in-image name from the host filename, stripping
            # any filename-encoded metadata suffix (,xxx or ,load,exec).
            leaf = entry.name.split(",", 1)[0]
            target = mount.join(parent_path, leaf)
            _clean, _label, meta = import_with_metadata(entry, meta_formats=meta_formats)
            mount.write_bytes(target, entry.read_bytes())
            if isinstance(mount, AcornMetadata):
                mount.set_acorn_meta(
                    target,
                    AcornMeta(
                        load_address=meta.load_address or 0,
                        exec_address=meta.exec_address or 0,
                        access=int(meta.access) if meta.access is not None else 0,
                    ),
                )
            if verbose:
                click.echo(leaf, err=True)
        elif entry.is_dir():
            if flat:
                # A flat catalogue (DFS) imports files from subdirectories
                # directly into the same directory.
                _import_host_dir(mount, parent_path, entry, meta_formats, verbose)
            else:
                sub = mount.join(parent_path, entry.name)
                mount.make_directory(sub, exist_ok=True)
                _import_host_dir(mount, sub, entry, meta_formats, verbose)


# ---------------------------------------------------------------------------
# AFS-specific commands
# ---------------------------------------------------------------------------


@cli.command(name="afs-plan")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--cylinders",
    type=int,
    default=None,
    help="Proposed AFS region size in cylinders.",
)
@click.option(
    "--compact",
    is_flag=True,
    default=False,
    help="Plan with ADFS compaction to maximise AFS space.",
)
@report_output(
    reports={
        "geometry": "Disc geometry.",
        "adfs_state": "ADFS occupancy.",
        "existing_afs": "Existing AFS partition (only when one is already installed).",
        "plan": "Proposed new AFS partition (only when computable).",
    }
)
def afs_plan(
    image: Path,
    cylinders: int | None,
    compact: bool,
):
    """Show what afs-init would do, without modifying the image.

    By default, plans using the existing tail free extent (matching
    WFSINIT behaviour). With --compact, plans a compaction-first
    layout that reclaims the maximum space. With --cylinders N,
    shows the plan for that specific size. Reports disc geometry,
    current ADFS occupancy, whether compaction is needed, and the
    resulting partition layout.

    Use ``--as json`` to emit a machine-readable document instead
    of the human-readable display report.
    """
    from oaknut.adfs import ADFS
    from oaknut.afs.wfsinit import AFSSizeSpec
    from oaknut.afs.wfsinit.partition import plan

    with ADFS.from_file(image) as adfs:
        geom = adfs.geometry
        total_sectors = geom.total_sectors
        free_bytes = adfs.free_space
        free_sectors = free_bytes // 256
        used_sectors = total_sectors - free_sectors

        document: dict = {
            "image": str(image),
            "geometry": {
                "cylinders": geom.cylinders,
                "heads": geom.heads,
                "sectors_per_track": geom.sectors_per_track,
                "total_sectors": total_sectors,
                "total_bytes": total_sectors * 256,
            },
            "adfs": {
                "used_sectors": used_sectors,
                "free_sectors": free_sectors,
                "free_bytes": free_bytes,
            },
        }

        # Check for existing AFS partition.
        sec1, sec2 = adfs._fsm.afs_info_pointers
        if sec1 != 0 or sec2 != 0:
            existing: dict = {"present": True}
            if adfs.has_afs_partition:
                afs = adfs.afs_partition
                existing["disc_name"] = afs.disc_name
                existing["start_cylinder"] = afs.start_cylinder
            document["existing_afs"] = existing
            return _build_afs_plan_reports(document)

        document["existing_afs"] = {"present": False}

        # Compute the plan using the same defaults as afs-init:
        # existing_free() without compaction (matching WFSINIT), or
        # max() with compaction when --compact is given.
        if cylinders:
            size = AFSSizeSpec.cylinders(cylinders)
        elif compact:
            size = AFSSizeSpec.max()
        else:
            size = AFSSizeSpec.existing_free()
        try:
            p = plan(adfs, size=size, compact_adfs=compact)
        except Exception as exc:
            raise click.ClickException(str(exc))

        document["plan"] = {
            "afs_cylinders": p.afs_cylinders,
            "total_afs_sectors": p.total_afs_sectors,
            "total_afs_bytes": p.total_afs_sectors * 256,
            "start_cylinder": p.start_cylinder,
            "new_adfs_cylinders": p.new_adfs_cylinders,
            "will_compact": p.will_compact,
            "compact_requested": compact,
            "cylinders_requested": cylinders,
        }

        if not cylinders:
            compact_flag = " --compact" if compact else ""
            document["suggested_command"] = (
                f"disc afs-init {image} --disc-name NAME"
                f" --cylinders {p.afs_cylinders}{compact_flag}"
            )

        return _build_afs_plan_reports(document)


def _build_afs_plan_reports(document: dict):
    """Build a Reports collection from the afs-plan document dict.

    One report per document section: ``geometry``, ``adfs_state``,
    optionally ``existing_afs`` (only when an AFS partition is
    already installed) or ``plan`` (only when computed).  The
    transposed single-row table shape turns each section into a
    key-value block in display mode and ``field\\tvalue`` lines in
    TSV.
    """
    from asyoulikeit.tabular_data import Report, Reports

    sections: dict = {}
    geom = document["geometry"]
    sections["geometry"] = Report(
        data=_kv_table(
            "Disc geometry",
            [
                (
                    "shape",
                    "Shape",
                    f"{geom['cylinders']} cylinders, "
                    f"{geom['heads']} heads, "
                    f"{geom['sectors_per_track']} sectors/track",
                ),
                (
                    "total",
                    "Total",
                    f"{geom['total_sectors']} sectors ({geom['total_bytes']:,} bytes)",
                ),
            ],
        )
    )

    adfs_state = document["adfs"]
    sections["adfs_state"] = Report(
        data=_kv_table(
            "ADFS occupancy",
            [
                ("used_sectors", "Used sectors", str(adfs_state["used_sectors"])),
                ("free_sectors", "Free sectors", str(adfs_state["free_sectors"])),
                ("free_bytes", "Free bytes", f"{adfs_state['free_bytes']:,}"),
            ],
        )
    )

    existing = document["existing_afs"]
    if existing["present"]:
        pairs = [("present", "Present", "yes")]
        if "disc_name" in existing:
            pairs.append(("disc_name", "Disc name", existing["disc_name"]))
            pairs.append(("start_cylinder", "Start cylinder", str(existing["start_cylinder"])))
        sections["existing_afs"] = Report(data=_kv_table("Existing AFS partition", pairs))
        return Reports(sections)

    p = document["plan"]
    plan_pairs = [
        (
            "afs_region",
            "AFS region",
            f"{p['afs_cylinders']} cylinders "
            f"({p['total_afs_sectors']} sectors, "
            f"{p['total_afs_bytes']:,} bytes)",
        ),
        ("start_cylinder", "Start cylinder", str(p["start_cylinder"])),
        ("new_adfs_cylinders", "ADFS retained", f"{p['new_adfs_cylinders']} cylinders"),
        (
            "will_compact",
            "Compaction",
            "required" if p["will_compact"] else "not required",
        ),
    ]
    if "suggested_command" in document:
        plan_pairs.append(("suggested_command", "Suggested command", document["suggested_command"]))
    sections["plan"] = Report(data=_kv_table("Proposed AFS partition", plan_pairs))
    return Reports(sections)


@cli.command(name="afs-init")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option("--disc-name", required=True, help="AFS disc name.")
@click.option(
    "--cylinders",
    type=int,
    default=None,
    help="AFS region size in cylinders (default: use existing free space).",
)
@click.option(
    "--compact",
    is_flag=True,
    default=False,
    help="Compact the ADFS partition first to maximise AFS space.",
)
@click.option(
    "--user",
    "users",
    multiple=True,
    help=(
        "User spec as NAME, NAME:S (system), NAME:QUOTA, "
        "or NAME:S:QUOTA. Quota accepts e.g. 2MiB. Repeat for multiple. "
        "A NAME matching a built-in (Syst, Boot, Welcome) overrides "
        "that built-in's quota; Syst requires :S. Set passwords with "
        "--user-password, not here."
    ),
)
@click.option(
    "--user-password",
    "user_passwords",
    multiple=True,
    metavar="NAME=VALUE",
    help=(
        "Set a user's password as NAME=VALUE, split once on the first "
        "'=' so the password may itself contain ':' or '='. NAME must "
        "match a --user or a built-in (Syst, Boot, Welcome). Repeat for "
        "multiple. Passwords are stored as cleartext (max 6 ASCII chars)."
    ),
)
@click.option(
    "--default-quota",
    default=None,
    help="Default quota for users without an explicit quota (e.g. 256KiB).",
)
@click.option(
    "--omit-user",
    "omit_users",
    multiple=True,
    help="Suppress a built-in account (Syst, Boot, or Welcome). Repeat for multiple.",
)
@click.option(
    "--emplace",
    "emplacements",
    multiple=True,
    help=(
        "Emplace a library: a shipped name (Library, Library1, ArthurLib) "
        "or a path to an ADFS .adl image. Repeat for multiple."
    ),
)
def afs_init(
    image: Path,
    disc_name: str,
    cylinders: int | None,
    compact: bool,
    users: tuple[str, ...],
    user_passwords: tuple[str, ...],
    default_quota: str | None,
    omit_users: tuple[str, ...],
    emplacements: tuple[str, ...],
) -> None:
    """Initialise an AFS partition on an ADFS hard disc image."""
    from oaknut.adfs import ADFS
    from oaknut.afs.exceptions import AFSInitSpecError
    from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise

    try:
        user_specs: list[UserSpec] = _parse_user_specs(users)
        user_specs = _apply_user_passwords(user_specs, user_passwords)

        init_kwargs: dict = {
            "disc_name": disc_name,
            "users": user_specs,
            "omit_builtins": frozenset(omit_users),
        }
        if cylinders:
            init_kwargs["size"] = AFSSizeSpec.cylinders(cylinders)
        if compact:
            init_kwargs["compact_adfs"] = True
            # When compacting, default to max space unless cylinders given.
            if "size" not in init_kwargs:
                init_kwargs["size"] = AFSSizeSpec.max()
        if default_quota is not None:
            from oaknut.file.capacity import parse_capacity

            try:
                init_kwargs["default_quota"] = parse_capacity(default_quota)
            except ValueError as exc:
                raise click.ClickException(str(exc))

        spec = InitSpec(**init_kwargs)
    except AFSInitSpecError as exc:
        raise click.ClickException(str(exc))

    with ADFS.from_file(image) as adfs:
        initialise(adfs, spec=spec)

        # Emplace libraries after initialisation so we can report
        # replacements to the user.
        if emplacements:
            from oaknut.afs.libraries import emplace_library

            with adfs.open_afs_partition() as afs:
                for name in emplacements:
                    try:
                        replaced = emplace_library(afs, name)
                    except (ValueError, FileNotFoundError) as exc:
                        raise click.ClickException(str(exc))
                    if replaced:
                        for fname in replaced:
                            click.echo(f"  replaced $.{name}/{fname}", err=True)


def _parse_user_specs(raw_specs: tuple[str, ...]) -> list:
    """Parse user specs from command-line strings.

    Accepted forms::

        NAME            — plain user
        NAME:S          — system user
        NAME:2MiB       — user with explicit quota
        NAME:S:2MiB     — system user with explicit quota
    """
    from oaknut.afs.wfsinit import UserSpec
    from oaknut.file.capacity import parse_capacity

    specs: list[UserSpec] = []
    for raw in raw_specs:
        parts = raw.split(":")
        name = parts[0]
        system = False
        quota = None
        for part in parts[1:]:
            if part.upper() == "S":
                system = True
            else:
                try:
                    quota = parse_capacity(part)
                except ValueError:
                    raise click.ClickException(
                        f"unrecognised user spec component '{part}' in '{raw}'"
                    )
        kwargs: dict = {"name": name, "system": system}
        if quota is not None:
            kwargs["quota"] = quota
        specs.append(UserSpec(**kwargs))
    return specs


def _apply_user_passwords(user_specs: list, raw_passwords: tuple[str, ...]) -> list:
    """Merge ``--user-password NAME=VALUE`` specs into ``user_specs``.

    Each raw string is split **once** on the first ``=``: the left side
    is the user name (the constrained key) and the right side is the
    password, taken verbatim — so it may itself contain ``:`` or ``=``.
    A name matching an existing ``--user`` spec sets that spec's
    password; a name matching a built-in (Syst/Boot/Welcome) synthesises
    an override spec with the built-in's required system flag; any other
    name is an error.
    """
    if not raw_passwords:
        return user_specs

    import dataclasses

    from oaknut.afs.wfsinit import (
        BUILTIN_ACCOUNT_NAMES,
        UserSpec,
        builtin_account_system_flag,
    )

    builtin_by_upper = {n.upper(): n for n in BUILTIN_ACCOUNT_NAMES}
    spec_index_by_upper = {spec.name.upper(): i for i, spec in enumerate(user_specs)}
    specs = list(user_specs)
    seen: set[str] = set()

    for raw in raw_passwords:
        name, separator, password = raw.partition("=")
        if not separator:
            raise click.ClickException(f"--user-password must be NAME=VALUE, got {raw!r}")
        if not name:
            raise click.ClickException(f"--user-password has an empty user name: {raw!r}")
        upper = name.upper()
        if upper in seen:
            raise click.ClickException(f"duplicate --user-password for {name!r}")
        seen.add(upper)

        if upper in spec_index_by_upper:
            index = spec_index_by_upper[upper]
            specs[index] = dataclasses.replace(specs[index], password=password)
        elif upper in builtin_by_upper:
            canonical = builtin_by_upper[upper]
            specs.append(
                UserSpec(
                    name=canonical,
                    password=password,
                    system=builtin_account_system_flag(canonical),
                )
            )
            spec_index_by_upper[upper] = len(specs) - 1
        else:
            raise click.ClickException(
                f"--user-password names {name!r}, which is neither a --user "
                f"nor a built-in account ({', '.join(sorted(BUILTIN_ACCOUNT_NAMES))})"
            )
    return specs


@cli.command(name="afs-users")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@report_output(reports={"users": "Users with system flag and quota."})
def afs_users(image: Path):
    """List AFS users with quota and flags."""
    from asyoulikeit.tabular_data import Report, Reports, TableContent

    table = TableContent(title="users")
    table.add_column("user", "User", header=True)
    table.add_column("system", "System")
    table.add_column("quota", "Quota")

    with _open_afs(image) as afs:
        for u in afs.users.active:
            table.add_row(
                user=u.full_id,
                system="yes" if u.is_system else "",
                # A quota is a byte count: humans want friendly units,
                # machines want the raw number. ByAudience carries both,
                # and the selected formatter's audience picks one.
                quota=ByAudience(
                    machine=u.free_space,
                    human=format_capacity(u.free_space),
                ),
            )
    return Reports(users=Report(data=table))


@cli.command(name="afs-useradd")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("name")
@click.option("--system", is_flag=True, help="System user flag.")
@click.option("--quota", type=int, default=None, help="Quota in bytes.")
@click.option("--password", default="", help="Initial password.")
def afs_useradd(
    image: Path,
    name: str,
    system: bool,
    quota: int | None,
    password: str,
) -> None:
    """Add a user to the AFS passwords file."""
    with open_image_for_afs_write(image) as (adfs, afs):
        afs.add_user(
            name,
            system=system,
            password=password,
            quota=quota or 0,
        )


@cli.command(name="afs-userdel")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("name")
def afs_userdel(image: Path, name: str) -> None:
    """Remove a user from the AFS passwords file."""
    with open_image_for_afs_write(image) as (adfs, afs):
        afs.remove_user(name)


@cli.command(name="afs-passwd")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("name")
@click.option("--password", required=True, help="New password (max 6 ASCII chars).")
def afs_passwd(image: Path, name: str, password: str) -> None:
    """Change an existing AFS user's login password.

    The Level 3 File Server stores passwords as up to six cleartext
    ASCII characters; there is no encryption. Unlike afs-useradd this
    only rewrites an existing record in place, so it never grows the
    passwords file.
    """
    with open_image_for_afs_write(image) as (adfs, afs):
        afs.set_password(name, password)


@cli.command(name="afs-merge")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Source AFS image to merge from.",
)
@click.option("--target-path", default=None, help="Target AFS path for merge root.")
@click.option(
    "--on-conflict",
    type=click.Choice(["error", "skip", "overwrite"], case_sensitive=False),
    default="error",
    show_default=True,
    help="Policy when a source entry's name already exists on the target.",
)
def afs_merge(
    image: Path,
    source: Path,
    target_path: str | None,
    on_conflict: str,
) -> None:
    """Bulk-copy the AFS file tree from one image into another.

    Walks the source AFS partition recursively and recreates every
    directory and file under the target's AFS partition, preserving
    each entry's access byte, load address, exec address, and date.
    The source image is opened read-only; only the target is mutated.

    Typical uses:

    \b
      - layering a shipped library image (``Library``, ``ArthurLib``,
        ``Library1``) onto a server disc after the fact, when
        ``afs-init --emplace`` was not used at creation time;
      - consolidating two Level 3 File Server discs onto one image,
        either at the AFS root or — with ``--target-path`` — under a
        chosen subdirectory of the target's namespace.

    The ``Passwords`` file is always excluded so the target's own
    user records survive intact.

    The ``--on-conflict`` policy chooses what happens when a source
    entry's name already exists on the target:

    \b
      - ``error`` (default): abort the whole merge before writing
        anything, so no partial state lands on disc;
      - ``skip``: keep the target's existing entry, drop the source's;
      - ``overwrite``: replace the target's entry with the source's
        (the old bytes are released back to the allocator).
    """
    from oaknut.adfs import ADFS
    from oaknut.afs import merge

    with (
        ADFS.from_file(image) as target_adfs,
        target_adfs.open_afs_partition() as target_afs,
        ADFS.from_file(source) as source_adfs,
        source_adfs.open_afs_partition() as source_afs,
    ):
        target_root = target_afs.root
        if target_path:
            target_root = _navigate_afs(target_afs, target_path)

        merge(
            target_afs,
            source_afs,
            target_path=target_root,
            conflict=on_conflict.lower(),
        )


# ---------------------------------------------------------------------------
# generate-dsc
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Filesystem-contributed commands
# ---------------------------------------------------------------------------
# Each installed filesystem package may contribute admin subcommands — e.g.
# `disc afs init`, `disc adfs generate-dsc`, `disc dfs expand` — on the
# `oaknut.command` axis. Attach them to the root group; they inherit the
# handled_errors boundary, `--debug`, and exit codes because AliasGroup.invoke
# wraps the whole dispatch (including nested groups).
for _contributed_command in contributed_commands():
    cli.add_command(_contributed_command)

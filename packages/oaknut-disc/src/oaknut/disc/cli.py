"""Click command-line interface for the unified disc tool.

Provides a single ``disc`` / ``oaknut-disc`` entry point for working
with Acorn DFS, ADFS, and AFS disc images. See ``docs/cli-design.md``
for the design rationale.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import click
from asyoulikeit.cli import report_output

from . import __version__
from .cli_paths import FilingSystem, detect_filing_system, parse_prefix, resolve_path

# ---------------------------------------------------------------------------
# Alias-aware Click group
# ---------------------------------------------------------------------------

_ALIASES: dict[str, str] = {}


class AliasGroup(click.Group):
    """Click group that supports star-prefixed Acorn aliases."""

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
    """Format an access attribute for display.

    DFS and ADFS use the wire-form ``oaknut.file.Access`` bit layout
    and are rendered via :func:`oaknut.file.format_access_text`.  AFS
    stores its access byte in a different bit layout
    (:class:`oaknut.afs.access.AFSAccess`) — passing that through the
    wire renderer would silently produce wrong strings (issue #12),
    so an ``AFSAccess`` is routed through its own ``to_string``.
    """
    from oaknut.afs.access import AFSAccess
    from oaknut.file import format_access_text

    if isinstance(access, AFSAccess):
        return access.to_string()
    return format_access_text(access)


def _access_byte_hex(stat_obj) -> str:
    """Two-digit hex for the raw access byte, with a ``0x`` prefix.

    Used by ``ls --access-byte`` (issue #10).  The prefix makes the
    value unambiguously hex and directly copy-pasteable into
    ``disc chmod path 0x..`` — a bare ``0D`` would also parse but
    is harder to read at a glance.  For DFS, which exposes
    ``stat.locked`` rather than a full access byte, the byte is
    synthesised as 0x08 when locked and 0x00 otherwise.
    """
    from oaknut.file import Access

    if hasattr(stat_obj, "access"):
        return f"0x{int(stat_obj.access):02X}"
    if getattr(stat_obj, "locked", False):
        return f"0x{int(Access.L):02X}"
    return "0x00"


# ---------------------------------------------------------------------------
# DFS format detection (extension + file size)
# ---------------------------------------------------------------------------


def _detect_dfs_format(image_filepath: Path):
    """Detect DFS disc format from file extension and size.

    Handles standard sizes (40T/80T) and also short/truncated .ssd
    images that contain fewer sectors than a full disc.
    """
    from oaknut.dfs import (
        ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
        ACORN_DFS_40T_SINGLE_SIDED,
        ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
        ACORN_DFS_80T_SINGLE_SIDED,
        DiskFormat,
    )
    from oaknut.discimage.formats import SurfaceSpec

    size = image_filepath.stat().st_size
    ext = image_filepath.suffix.lower()

    if ext == ".ssd":
        if size == 102400:
            return ACORN_DFS_40T_SINGLE_SIDED
        if size == 204800:
            return ACORN_DFS_80T_SINGLE_SIDED
        # Non-standard (short or padded) SSD — build a format that
        # matches the actual file size. The catalogue type is always
        # Acorn DFS for .ssd files.
        if size % 256 != 0:
            raise click.ClickException(
                f"SSD image size ({size}) is not a multiple of 256 bytes"
            )
        total_sectors = size // 256
        return DiskFormat(
            surface_specs=[
                SurfaceSpec(
                    num_tracks=1,
                    sectors_per_track=total_sectors,
                    bytes_per_sector=256,
                    track_zero_offset_bytes=0,
                    track_stride_bytes=size,
                )
            ],
            catalogue_name="acorn-dfs",
        )
    elif ext == ".dsd":
        if size <= 204800:
            return ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED
        return ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED

    raise click.ClickException(f"cannot detect DFS format for '{image_filepath.name}'")


# ---------------------------------------------------------------------------
# Image openers — context managers returning (fs_handle, filing_system)
# ---------------------------------------------------------------------------


@contextmanager
def _open_dfs(image_filepath: Path, mode: str = "rb") -> Iterator:
    """Open image as DFS, yielding the DFS handle."""
    from oaknut.dfs import DFS

    disk_format = _detect_dfs_format(image_filepath)
    with DFS.from_file(image_filepath, disk_format, mode=mode) as dfs:
        yield dfs


@contextmanager
def _open_adfs(image_filepath: Path, mode: str = "rb") -> Iterator:
    """Open image as ADFS, yielding the ADFS handle."""
    from oaknut.adfs import ADFS

    with ADFS.from_file(image_filepath, mode=mode) as adfs:
        yield adfs


@contextmanager
def _open_afs(image_filepath: Path, mode: str = "rb") -> Iterator:
    """Open image as ADFS, grab the AFS partition, yield it.

    Raises :class:`click.ClickException` if no AFS partition is
    present.
    """
    from oaknut.adfs import ADFS

    with ADFS.from_file(image_filepath, mode=mode) as adfs:
        afs = adfs.afs_partition
        if afs is None:
            raise click.ClickException("no AFS partition found on this disc")
        yield afs


@contextmanager
def open_image(
    image_filepath: Path,
    fs: FilingSystem,
    mode: str = "rb",
) -> Iterator:
    """Open an image for the given filing system.

    Yields the appropriate handle (DFS, ADFS, or AFS).
    """
    if fs is FilingSystem.DFS:
        with _open_dfs(image_filepath, mode) as handle:
            yield handle
    elif fs is FilingSystem.ADFS:
        with _open_adfs(image_filepath, mode) as handle:
            yield handle
    elif fs is FilingSystem.AFS:
        with _open_afs(image_filepath, mode) as handle:
            yield handle


@contextmanager
def open_image_for_afs_write(image_filepath: Path) -> Iterator:
    """Open for AFS write: yields (adfs, afs) so the caller can flush."""
    from oaknut.adfs import ADFS

    with ADFS.from_file(image_filepath, mode="r+b") as adfs:
        afs = adfs.afs_partition
        if afs is None:
            raise click.ClickException("no AFS partition found on this disc")
        yield adfs, afs


def _navigate(handle, bare_path: str, fs: FilingSystem):
    """Navigate to a path within the filesystem handle.

    Returns the path object at *bare_path*, or the default root when
    *bare_path* is empty. For DFS, the default root is ``$`` (the
    directory that actually contains files), not the virtual root
    above it.
    """
    if not bare_path:
        return handle.root
    if fs is FilingSystem.AFS:
        return _navigate_afs(handle, bare_path)
    return handle.path(bare_path)


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


def _image_has_afs(image_filepath: "Path") -> bool:
    """Does the image carry an AFS partition alongside its ADFS one?

    Cheap probe: opens the image as ADFS and checks ``afs_partition``.
    Returns ``False`` for every non-ADFS format.
    """
    fs = detect_filing_system(image_filepath)
    if fs is not FilingSystem.ADFS:
        return False
    with _open_adfs(image_filepath) as adfs:
        return adfs.afs_partition is not None


def _iter_search_partitions(
    image_filepath: "Path",
    requested_fs: FilingSystem,
    prefix_present: bool,
) -> Iterator[FilingSystem]:
    """Yield each partition a find-style command should search.

    When the caller provided an explicit filing-system prefix
    (``adfs:``, ``afs:``, ``dfs:``), yield just that.  Otherwise, on
    a multi-partition image (ADFS + AFS on the same file), yield
    both partitions so a no-prefix ``disc find`` covers the whole
    image.  Single-partition images always yield one.
    """
    if prefix_present:
        yield requested_fs
        return
    if requested_fs is FilingSystem.ADFS and _image_has_afs(image_filepath):
        yield FilingSystem.ADFS
        yield FilingSystem.AFS
        return
    yield requested_fs


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group(cls=AliasGroup)
@click.version_option(version=__version__, prog_name="disc")
def cli() -> None:
    """Work with Acorn DFS, ADFS, and AFS disc images."""


# ---------------------------------------------------------------------------
# Inspection commands
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path", required=False, default=None)
@click.option(
    "-H",
    "--access-byte",
    "show_access_byte",
    is_flag=True,
    help="Show the raw access byte as two hex digits alongside the symbolic form.",
)
@report_output
def ls(image: Path, path: str | None, show_access_byte: bool):
    """List directory contents (Acorn alias: *CAT)."""
    from asyoulikeit.tabular_data import Importance, Report, Reports, TableContent

    fs, bare = resolve_path(image, path)
    with open_image(image, fs) as handle:
        target = _navigate(handle, bare, fs)

        if not target.exists() and not target.is_dir():
            raise click.ClickException(f"path not found: {bare or '$'}")

        if target.is_file():
            # Single file — just echo the bare name, same as before.
            # Skipping the Reports envelope keeps `disc ls img $.file`
            # shell-pipe-friendly without a header line to grep away.
            click.echo(target.name)
            return None

        entries = list(target.iterdir())

        # Build the display title and the "free space" description
        # from filing-system-specific handle attributes.
        if fs is FilingSystem.DFS:
            title_str = getattr(handle, "title", "") or ""
            free = getattr(handle, "free_sectors", None)
            free_unit = "sectors"
            fmt_name = "DFS"
        elif fs is FilingSystem.AFS:
            title_str = getattr(handle, "disc_name", "") or ""
            free = getattr(handle, "free_sectors", None)
            free_unit = "sectors"
            fmt_name = "AFS"
        else:
            title_str = getattr(handle, "title", "") or ""
            free = getattr(handle, "free_space", None)
            free_unit = "bytes"
            fmt_name = "ADFS"

        table_title = f"{image.name}"
        if title_str:
            table_title += f" — {title_str}"
        table_title += f" [{fmt_name}]"

        if free is not None:
            description = f"Free: {free:,} {free_unit}"
        else:
            description = None

        table = TableContent(title=table_title, description=description)
        table.add_column("name", "Name", header=True)
        # Load and exec are Acorn-specific addresses that matter in
        # display-focused use and are available via get-load/get-exec
        # on demand; drop them from TSV by default so the piped-output
        # view stays concise.  --detailed restores them.
        table.add_column("load", "Load", importance=Importance.DETAIL)
        table.add_column("exec", "Exec", importance=Importance.DETAIL)
        table.add_column("length", "Length")
        table.add_column("attr", "Attr")
        if show_access_byte:
            # The user explicitly asked for the raw byte — treat it
            # as essential so TSV shows it alongside Attr without
            # requiring --detailed too.
            table.add_column("hex", "Hex")

        for child in entries:
            if child.is_dir():
                row = {
                    "name": f"{child.name}/",
                    "load": "",
                    "exec": "",
                    "length": "",
                    "attr": "",
                }
                if show_access_byte:
                    row["hex"] = ""
                table.add_row(**row)
                continue
            st = child.stat()
            load_str = f"{st.load_address:08X}" if hasattr(st, "load_address") else ""
            exec_str = f"{st.exec_address:08X}" if hasattr(st, "exec_address") else ""
            length_str = f"{st.length:08X}" if hasattr(st, "length") else ""
            locked = getattr(st, "locked", False)
            attr_str = "L" if locked else ""
            if hasattr(st, "access"):
                attr_str = _format_access(st.access)
            row = {
                "name": child.name,
                "load": load_str,
                "exec": exec_str,
                "length": length_str,
                "attr": attr_str,
            }
            if show_access_byte:
                row["hex"] = _access_byte_hex(st)
            table.add_row(**row)

    return Reports(entries=Report(data=table))


_alias("*CAT", "ls")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path", required=False, default=None)
@report_output
def tree(image: Path, path: str | None):
    """Display recursive directory tree."""
    from asyoulikeit.tabular_data import Report, Reports
    from asyoulikeit.tree_data import TreeContent

    tc = TreeContent(title=image.name)
    tc.add_column("name", "Name", header=True)

    if path is not None:
        # Explicit path (possibly with FS prefix) — show that subtree only.
        fs, bare = resolve_path(image, path)
        with open_image(image, fs) as handle:
            root_node = _navigate(handle, bare, fs)
            if not root_node.exists() and not root_node.is_dir():
                raise click.ClickException(f"path not found: {bare or '$'}")
            root = tc.add_root(name=root_node.name)
            _attach_children(root_node, root)
    else:
        _build_tree_whole_image(image, tc)

    return Reports(tree=Report(data=tc))


def _build_tree_whole_image(image_filepath: Path, tc) -> None:
    """Populate *tc* with one root per image, labelled partitions beneath."""
    detected = detect_filing_system(image_filepath)
    image_root = tc.add_root(name=image_filepath.name)

    if detected is FilingSystem.DFS:
        with _open_dfs(image_filepath) as handle:
            _attach_children(handle.root, image_root)
        return

    with _open_adfs(image_filepath) as adfs:
        afs = adfs.afs_partition
        if afs is None:
            _attach_node(adfs.root, image_root)
        else:
            adfs_label = image_root.add_child(name="ADFS")
            _attach_node(adfs.root, adfs_label)
            afs_label = image_root.add_child(name="AFS")
            _attach_node(afs.root, afs_label)


def _attach_node(fs_node, parent_tree_node) -> None:
    """Attach ``fs_node`` as a child of ``parent_tree_node`` and recurse."""
    child = parent_tree_node.add_child(name=fs_node.name)
    if fs_node.is_dir():
        _attach_children(fs_node, child)


def _attach_children(dir_node, parent_tree_node) -> None:
    """Attach every child of ``dir_node`` under ``parent_tree_node``."""
    for child in dir_node.iterdir():
        _attach_node(child, parent_tree_node)


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path", required=False, default=None)
@report_output
def stat(image: Path, path: str | None):
    """Disc summary (no path) or file metadata (with path). Alias: *INFO."""
    from asyoulikeit.tabular_data import Report, Reports, TableContent

    fs, bare = resolve_path(image, path)

    if not bare:
        return _stat_disc(image, fs)

    with open_image(image, fs) as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        st = target.stat()

        tc = TableContent(title=f"{target.name}", present_transposed=True)
        tc.add_column("name", "Name", header=True)
        row: dict = {"name": target.name}
        if hasattr(st, "load_address"):
            tc.add_column("load", "Load")
            row["load"] = f"{st.load_address:08X}"
        if hasattr(st, "exec_address"):
            tc.add_column("exec", "Exec")
            row["exec"] = f"{st.exec_address:08X}"
        if hasattr(st, "length"):
            tc.add_column("length", "Length")
            row["length"] = f"{st.length:08X}"
        if hasattr(st, "access"):
            tc.add_column("attr", "Attr")
            row["attr"] = _format_access(st.access)
        elif getattr(st, "locked", False):
            tc.add_column("attr", "Attr")
            row["attr"] = "L"
        if hasattr(st, "is_directory"):
            tc.add_column("dir", "Dir")
            row["dir"] = "yes" if st.is_directory else "no"
        tc.add_row(**row)
        return Reports(file=Report(data=tc))


_alias("*INFO", "stat")


_SECTOR_SIZE = 256


def _stat_disc(image_filepath: Path, fs: FilingSystem):
    """Build the whole-disc summary as a Reports collection.

    The layout is a disc-level block (physical geometry + total size,
    both derived from the geometry so they stay self-consistent — see
    issue #7) followed by one ``partition_N`` block per filing-system
    partition on the image.

    When the user scopes the view with an ``afs:`` prefix, ``fs`` is
    :data:`FilingSystem.AFS` and a flat single-partition report is
    returned instead — the prefix is a deliberate drill-down.
    """
    from asyoulikeit.tabular_data import Report, Reports

    sections: dict = {}
    with open_image(image_filepath, fs) as handle:
        if fs is FilingSystem.AFS:
            sections["partition"] = Report(data=_afs_partition_only_tc(handle))
        elif fs is FilingSystem.DFS:
            sections["disc"] = Report(data=_disc_header_dfs_tc(handle))
            sections["partition_1"] = Report(data=_dfs_partition_tc(handle))
        else:
            sections["disc"] = Report(data=_disc_header_adfs_tc(handle))
            sections["partition_1"] = Report(data=_adfs_partition_tc(handle))
            afs = handle.afs_partition
            if afs is not None:
                sections["partition_2"] = Report(
                    data=_afs_partition_tc(handle, afs)
                )
    return Reports(sections)


def _format_size(sectors: int) -> str:
    """Consistent ``X bytes (Y sectors)`` rendering."""
    return f"{sectors * _SECTOR_SIZE:,} bytes ({sectors} sectors)"


def _kv_table(title: str, pairs: list[tuple[str, str, str]]):
    """Build a transposed single-row table from (key, label, value) tuples.

    Each tuple becomes a column whose sole row holds the rendered value.
    Transposed presentation turns the one-row table into a key-value
    report in the display formatter.
    """
    from asyoulikeit.tabular_data import TableContent

    tc = TableContent(title=title, present_transposed=True)
    row: dict = {}
    for i, (key, label, value) in enumerate(pairs):
        tc.add_column(key, label, header=(i == 0))
        row[key] = value
    tc.add_row(**row)
    return tc


def _disc_header_dfs_tc(handle):
    total_sectors = handle.info["total_sectors"]
    return _kv_table(
        "Disc",
        [("size", "Size", _format_size(total_sectors))],
    )


def _disc_header_adfs_tc(handle):
    geom = handle.geometry
    total_sectors = geom.cylinders * geom.heads * geom.sectors_per_track
    return _kv_table(
        "Disc",
        [
            (
                "geometry",
                "Geometry",
                f"{geom.cylinders} cylinders, {geom.heads} heads, "
                f"{geom.sectors_per_track} sectors/track",
            ),
            ("size", "Size", _format_size(total_sectors)),
        ],
    )


def _dfs_partition_tc(handle):
    from oaknut.file import BootOption

    info = handle.info
    boot = BootOption(handle.boot_option)
    return _kv_table(
        "Partition 1: DFS",
        [
            ("title", "Title", handle.title or ""),
            ("boot_option", "Boot option", f"{boot.name} ({boot.value})"),
            ("size", "Size", _format_size(info["total_sectors"])),
            ("free", "Free", _format_size(info["free_sectors"])),
            ("files", "Files", str(info["num_files"])),
        ],
    )


def _adfs_partition_tc(handle):
    from oaknut.file import BootOption

    geom = handle.geometry
    adfs_sectors = handle.total_size // _SECTOR_SIZE
    adfs_cylinders = adfs_sectors // (geom.heads * geom.sectors_per_track)
    boot = BootOption(handle.boot_option)
    pairs: list[tuple[str, str, str]] = [
        ("title", "Title", handle.title or ""),
        ("boot_option", "Boot option", f"{boot.name} ({boot.value})"),
    ]
    if adfs_cylinders < geom.cylinders:
        pairs.append(
            ("range", "Range", f"cylinders 0-{adfs_cylinders - 1}")
        )
    pairs.append(("size", "Size", _format_size(adfs_sectors)))
    free_sectors = handle.free_space // _SECTOR_SIZE
    pairs.append(("free", "Free", _format_size(free_sectors)))
    return _kv_table("Partition 1: ADFS", pairs)


def _afs_partition_tc(adfs_handle, afs):
    geom = adfs_handle.geometry
    afs_cylinders = geom.cylinders - afs.start_cylinder
    afs_sectors = afs_cylinders * geom.heads * geom.sectors_per_track
    return _kv_table(
        "Partition 2: AFS",
        [
            ("disc_name", "Disc name", afs.disc_name),
            (
                "range",
                "Range",
                f"cylinders {afs.start_cylinder}-{geom.cylinders - 1}",
            ),
            ("size", "Size", _format_size(afs_sectors)),
            ("free", "Free", _format_size(afs.free_sectors)),
        ],
    )


def _afs_partition_only_tc(handle):
    """Flat AFS-scoped view for ``disc stat image afs:``."""
    geom = handle.geometry
    return _kv_table(
        "AFS",
        [
            ("disc_name", "Disc name", handle.disc_name),
            ("start_cylinder", "Start cylinder", str(handle.start_cylinder)),
            ("cylinders", "Cylinders", str(geom.cylinders)),
            ("sectors_per_cylinder", "Sectors/cyl", str(geom.sectors_per_cylinder)),
            ("total_sectors", "Total sectors", str(geom.total_sectors)),
            ("free_sectors", "Free sectors", str(handle.free_sectors)),
        ],
    )


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
def cat(image: Path, path: str) -> None:
    """Dump file contents to stdout (Acorn alias: *TYPE)."""
    fs, bare = resolve_path(image, path)
    with open_image(image, fs) as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        if target.is_dir():
            raise click.ClickException(f"'{bare}' is a directory")
        sys.stdout.buffer.write(target.read_bytes())


_alias("*TYPE", "cat")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("pattern")
@report_output
def find(image: Path, pattern: str):
    """Find files matching an Acorn wildcard pattern.

    Accepts the same ``adfs:`` / ``afs:`` / ``dfs:`` prefixes as
    every other command to scope the search to a single partition.
    Without a prefix, partitioned hard-disc images (ADFS + AFS) are
    searched in their entirety and each result is emitted with the
    partition prefix that would feed back into a follow-up command
    unchanged.  Single-partition images emit bare paths, unchanged
    from earlier behaviour.
    """
    from asyoulikeit.tabular_data import Report, Reports, TableContent

    from .cli_paths import parse_prefix

    prefix_present = parse_prefix(pattern)[0] is not None
    fs, bare_pattern = resolve_path(image, pattern)
    emit_prefix = _image_has_afs(image) if not prefix_present else True

    rows: list[dict] = []
    for partition_fs in _iter_search_partitions(image, fs, prefix_present):
        with open_image(image, partition_fs) as handle:
            prefix = f"{partition_fs.value}:" if emit_prefix else ""
            _find_recursive(handle.root, bare_pattern, prefix, rows)

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


def _find_recursive(node, pattern: str, prefix: str, rows: list[dict]) -> None:
    """Walk a directory tree, collecting paths matching *pattern*.

    ``prefix`` is prepended to each emitted path — empty on a
    single-partition image, ``adfs:`` / ``afs:`` / ``dfs:`` on a
    partitioned one — so every row is directly consumable by a
    follow-up command.
    """
    for child in node.iterdir():
        name = child.name
        path_str = child.path
        if _match_acorn_wildcard(pattern, name) or _match_acorn_wildcard(pattern, path_str):
            rows.append({"path": f"{prefix}{path_str}"})
        if child.is_dir():
            _find_recursive(child, pattern, prefix, rows)


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path", required=False, default=None)
def freemap(image: Path, path: str | None) -> None:
    """Show free-space map with ASCII fragmentation bar."""
    fs, bare = resolve_path(image, path)

    with open_image(image, fs) as handle:
        if fs is FilingSystem.DFS:
            _freemap_dfs(handle)
        elif fs is FilingSystem.AFS:
            _freemap_afs(handle)
        else:
            _freemap_adfs(handle)


def _sector_bar(total: int, free_regions: list[tuple[int, int]], width: int = 64) -> str:
    """Build an ASCII bar showing sector usage.

    *free_regions* is a list of ``(start, length)`` in sector units.
    ``#`` = used, ``.`` = free.
    """
    if total == 0:
        return ""
    # Build a boolean bitmap: True = free.
    bitmap = [False] * total
    for start, length in free_regions:
        for s in range(start, min(start + length, total)):
            bitmap[s] = True

    # Scale to *width* characters.
    bar = []
    for col in range(width):
        lo = col * total // width
        hi = (col + 1) * total // width
        if hi <= lo:
            hi = lo + 1
        # If any sector in this column is free, show it as free.
        if any(bitmap[s] for s in range(lo, min(hi, total))):
            bar.append(".")
        else:
            bar.append("#")
    return "".join(bar)


def _freemap_dfs(handle) -> None:
    """DFS free-space map."""
    regions = handle._catalogued_surface.get_free_map()
    disk_info = handle._catalogued_surface.catalogue.get_disk_info()
    total = disk_info.total_sectors
    free = handle.free_sectors

    bar = _sector_bar(total, regions)
    click.echo(f"Sectors: 0{' ' * (len(bar) - 2)}{total}")
    click.echo(f"         {bar}")

    if regions:
        largest = max(length for _, length in regions)
        click.echo(
            f"Free: {free} sectors in {len(regions)} region(s) "
            f"(largest {largest} contiguous)"
        )
    else:
        click.echo("Free: 0 sectors")


def _freemap_adfs(handle) -> None:
    """ADFS free-space map using the old-map free_space_entries."""
    # Convert byte-addressed entries to sector-addressed.
    byte_entries = handle._fsm.free_space_entries()
    sector_entries = [(start // 256, length // 256) for start, length in byte_entries]
    total_sectors = handle._fsm.total_sectors
    free_bytes = handle.free_space

    bar = _sector_bar(total_sectors, sector_entries)
    click.echo(f"Sectors: 0{' ' * (len(bar) - 2)}{total_sectors}")
    click.echo(f"         {bar}")

    if sector_entries:
        largest = max(length for _, length in sector_entries)
        click.echo(
            f"Free: {free_bytes:,} bytes ({sum(n for _, n in sector_entries)} sectors) "
            f"in {len(sector_entries)} region(s) (largest {largest} contiguous)"
        )
    else:
        click.echo("Free: 0 bytes")


def _freemap_afs(handle) -> None:
    """AFS free-space map showing per-cylinder occupancy."""
    shadow = handle._bitmap_shadow()
    geom = handle.geometry
    spc = geom.sectors_per_cylinder
    start_cyl = handle.start_cylinder
    num_cylinders = geom.cylinders - start_cyl

    total_free = 0
    total_sectors = 0
    bar_chars = []
    for i in range(num_cylinders):
        bm = shadow.bitmap_for(i)
        free = bm.free_count()
        total_free += free
        total_sectors += spc
        # Proportional fill for this cylinder.
        if free == spc:
            bar_chars.append(".")
        elif free == 0:
            bar_chars.append("#")
        else:
            bar_chars.append(":")  # partially used

    bar = "".join(bar_chars)
    click.echo(f"Cylinders: {start_cyl}{' ' * max(0, len(bar) - 2)}{geom.cylinders}")
    click.echo(f"           {bar}")
    click.echo(f"Free: {total_free} sectors of {total_sectors} ({num_cylinders} cylinders)")
    click.echo("Legend: # = full, : = partial, . = empty")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
def validate(image: Path) -> None:
    """Validate disc image structure."""
    fs = detect_filing_system(image)
    if fs is FilingSystem.DFS:
        click.echo("DFS validation not yet implemented")
        return
    with open_image(image, fs) as handle:
        if hasattr(handle, "validate"):
            errors = handle.validate()
            if errors:
                for err in errors:
                    click.echo(f"Error: {err}", err=True)
                raise SystemExit(1)
            else:
                click.echo("OK")
        else:
            click.echo("Validation not available for this format")


# ---------------------------------------------------------------------------
# File I/O commands
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@click.argument("host_path", required=False, default=None, type=click.Path(path_type=Path))
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
def get(image: Path, path: str, host_path: Path | None, meta_format: str, owner: int) -> None:
    """Export a file from the image."""
    from oaknut.file import AcornMeta, MetaFormat, export_with_metadata

    fs, bare = resolve_path(image, path)
    with open_image(image, fs) as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        if target.is_dir():
            raise click.ClickException(f"'{bare}' is a directory")

        data = target.read_bytes()

        # Stdout mode.
        if host_path is not None and str(host_path) == "-":
            sys.stdout.buffer.write(data)
            return

        # Build metadata.
        st = target.stat()
        meta = AcornMeta(
            load_addr=getattr(st, "load_address", None),
            exec_addr=getattr(st, "exec_address", None),
            attr=int(st.access)
            if hasattr(st, "access")
            else (0x08 if getattr(st, "locked", False) else 0),
        )

        if host_path is None:
            host_path = Path(target.name)

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
            filename=target.name,
        )


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@click.argument("host_path", required=False, default=None, type=click.Path(path_type=Path))
@click.option("--load", "load_addr", type=str, default=None, help="Load address (hex).")
@click.option("--exec", "exec_addr", type=str, default=None, help="Exec address (hex).")
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
    image: Path,
    path: str,
    host_path: Path | None,
    load_addr: str | None,
    exec_addr: str | None,
    meta_format: str | None,
) -> None:
    """Import a file into the image."""
    fs, bare = resolve_path(image, path)

    # Default addresses: 0xFFFF matches the convention for text/data
    # files on DFS and ADFS where the address is not meaningful.
    _DEFAULT_ADDR = 0xFFFF

    # Read data.
    if host_path is not None and str(host_path) == "-":
        data = sys.stdin.buffer.read()
        resolved_load = int(load_addr, 0) if load_addr else _DEFAULT_ADDR
        resolved_exec = int(exec_addr, 0) if exec_addr else _DEFAULT_ADDR
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
        resolved_load = int(load_addr, 0) if load_addr else (meta.load_addr or 0)
        resolved_exec = int(exec_addr, 0) if exec_addr else (meta.exec_addr or 0)
    else:
        raise click.ClickException("HOST_PATH is required (or use - for stdin)")

    mode = "r+b"
    with open_image(image, fs, mode=mode) as handle:
        target = _navigate(handle, bare, fs)
        target.write_bytes(
            data,
            load_address=resolved_load,
            exec_address=resolved_exec,
        )
        if fs is FilingSystem.AFS:
            handle.flush()


# ---------------------------------------------------------------------------
# Modification commands
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("paths", nargs=-1, required=True)
@click.option("-f", "--force", is_flag=True, help="Ignore missing, override locks.")
@click.option("-r", "--recursive", is_flag=True, help="Remove directories recursively.")
@click.option("--dry-run", is_flag=True, help="Print what would be removed.")
def rm(image: Path, paths: tuple[str, ...], force: bool, recursive: bool, dry_run: bool) -> None:
    """Delete file(s) from the image (Acorn alias: *DELETE).

    Each PATH may contain Acorn wildcards (``*``, ``#``); ``-r``
    descends into directory matches and removes children before the
    directory itself.
    """
    fs_type = detect_filing_system(image)
    first_prefix: FilingSystem | None = None
    per_path: list[tuple[FilingSystem, str]] = []
    for p in paths:
        fs, bare = resolve_path(image, p)
        if first_prefix is None:
            first_prefix = fs
        per_path.append((fs, bare))

    mode = "rb" if dry_run else "r+b"
    fs = first_prefix or fs_type
    with open_image(image, fs, mode=mode) as handle:
        for path_fs, bare in per_path:
            # --force downgrades "no matches" to a no-op.
            try:
                targets = list(
                    _iter_targets(handle, bare, path_fs, recursive=recursive)
                )
            except click.ClickException:
                if force:
                    continue
                raise

            for target in targets:
                if target.is_dir() and not recursive:
                    raise click.ClickException(
                        f"'{target.path}' is a directory "
                        "(use -r to remove recursively)"
                    )
                if dry_run:
                    click.echo(f"would remove: {target.path}")
                    continue
                try:
                    if target.is_dir():
                        # ADFS / AFS need an explicit rmdir because
                        # unlink refuses on directories.  DFS
                        # "directories" are letter prefixes that
                        # vanish implicitly once their files are
                        # gone — no action needed.
                        if hasattr(target, "rmdir"):
                            target.rmdir()
                    else:
                        target.unlink()
                except Exception as exc:
                    if force and "locked" in str(exc).lower():
                        if hasattr(target, "unlock"):
                            target.unlock()
                        if target.is_dir() and hasattr(target, "rmdir"):
                            target.rmdir()
                        else:
                            target.unlink()
                    else:
                        raise click.ClickException(str(exc))

        if fs is FilingSystem.AFS and not dry_run:
            handle.flush()


_alias("*DELETE", "rm")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("src")
@click.argument("dst")
@click.option("-f", "--force", is_flag=True, help="Overwrite existing destination.")
def mv(image: Path, src: str, dst: str, force: bool) -> None:
    """Rename or move a file within the image (Acorn alias: *RENAME)."""
    fs, bare_src = resolve_path(image, src)
    _, bare_dst = parse_prefix(dst)

    with open_image(image, fs, mode="r+b") as handle:
        source = _navigate(handle, bare_src, fs)
        if not source.exists():
            raise click.ClickException(f"path not found: {bare_src}")
        source.rename(bare_dst)
        if fs is FilingSystem.AFS:
            handle.flush()


_alias("*RENAME", "mv")


@cli.command()
@click.argument("args", nargs=-1, required=True)
@click.option("-f", "--force", is_flag=True, help="Overwrite existing destination.")
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    help="Copy directories recursively.",
)
def cp(args: tuple[str, ...], force: bool, recursive: bool) -> None:
    """Copy file(s) or a tree within or between disc images.

    Acorn alias: *COPY.

    \b
    Colon syntax (preferred for cross-image):
      disc cp source.ssd:$.HELLO target.dat:$.HELLO

    \b
    Three-arg form (within one image):
      disc cp IMAGE SRC DST

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
    from .cli_paths import parse_image_path

    if len(args) == 2:
        src_parsed = parse_image_path(args[0])
        dst_parsed = parse_image_path(args[1])
        if src_parsed is not None and dst_parsed is not None:
            _cp_dispatch(
                src_parsed[0], src_parsed[1],
                dst_parsed[0], dst_parsed[1],
                force=force, recursive=recursive,
            )
            return
        if src_parsed is not None or dst_parsed is not None:
            raise click.ClickException(
                "when using image:path syntax, both source and destination must use it"
            )
        raise click.ClickException(
            "cp requires either image:path colon syntax or three arguments (IMAGE SRC DST)"
        )
    elif len(args) == 3:
        image = Path(args[0])
        if not image.is_file():
            raise click.ClickException(f"image not found: {args[0]}")
        _cp_dispatch(
            image, args[1], image, args[2],
            force=force, recursive=recursive,
        )
    else:
        raise click.ClickException(
            "cp takes 2 arguments (image:path image:path) or 3 (IMAGE SRC DST)"
        )


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


def _expand_path_spec(handle, bare: str, fs: FilingSystem) -> list:
    """Resolve a path specification to a list of existing path objects.

    Literal paths resolve to a one-element list.  Acorn wildcards
    (``*``, ``#``, ``?``) on the leaf component expand against the
    parent directory's children.  No-match is an error.
    """
    if _has_wildcard(bare):
        parent, leaf_pattern = _split_parent_leaf(bare)
        if _has_wildcard(parent):
            raise click.ClickException(
                f"wildcards in directory components are not supported: {bare!r}"
            )
        parent_node = _navigate(handle, parent, fs)
        if not parent_node.exists() or not parent_node.is_dir():
            raise click.ClickException(
                f"parent directory of glob does not exist: {parent or '$'!r}"
            )
        matches = [c for c in parent_node.iterdir() if _match_acorn(leaf_pattern, c.name)]
        if not matches:
            raise click.ClickException(f"no matches for {bare!r}")
        return matches
    node = _navigate(handle, bare, fs)
    if not node.exists():
        raise click.ClickException(f"path not found: {bare}")
    return [node]


def _iter_targets(
    handle,
    bare: str,
    fs: FilingSystem,
    *,
    recursive: bool,
) -> Iterator:
    """Enumerate targets for a bulk-mutating command.

    Expands Acorn wildcards on ``bare`` and, when ``recursive`` is
    true, walks each directory match in post-order (children first,
    then the directory itself).  When ``recursive`` is false, each
    match is yielded once — callers decide whether to accept
    directory matches.

    Post-order is the right traversal order for ``rm -r`` (children
    must be deleted before their parent) and also works for
    ``chmod`` / ``lock`` / ``set-*`` where order doesn't matter.
    """
    for seed in _expand_path_spec(handle, bare, fs):
        if seed.is_dir() and recursive:
            yield from _walk_post_order(seed)
        else:
            yield seed


def _walk_post_order(node) -> Iterator:
    """Yield every descendant of ``node``, children before parents."""
    if node.is_file():
        yield node
        return
    for child in node.iterdir():
        yield from _walk_post_order(child)
    yield node


def _cp_dispatch(
    src_image: Path,
    src_spec: str,
    dst_image: Path,
    dst_spec: str,
    *,
    force: bool,
    recursive: bool,
) -> None:
    """Orchestrate a cp invocation.

    Handles single-file copy (the existing cases), wildcard
    expansion on the source, recursive directory copy, and the
    combination of the two.  Source data is buffered in memory
    during traversal so the source image is only held open while
    we're reading; the destination is opened fresh afterwards.
    """
    src_fs, src_bare = resolve_path(src_image, src_spec)
    dst_fs, dst_bare_raw = resolve_path(dst_image, dst_spec)
    dst_bare, dst_slash = _dst_ends_slash(dst_bare_raw)

    src_glob = _has_wildcard(src_bare)

    # --- Read phase: open source, collect one or more copy items. ---
    with open_image(src_image, src_fs) as src_handle:
        items = _collect_copy_items(
            src_handle, src_bare, src_fs,
            dst_bare=dst_bare,
            dst_slash=dst_slash,
            dst_image=dst_image,
            dst_fs=dst_fs,
            recursive=recursive,
            src_glob=src_glob,
        )

    # --- Write phase: open destination, apply each item. ---
    with open_image(dst_image, dst_fs, mode="r+b") as dst_handle:
        for item in items:
            kind = item["kind"]
            dst_path = item["dst"]
            if kind == "mkdir":
                _ensure_dir_chain(dst_handle, dst_path, dst_fs)
                continue
            if kind == "file":
                _write_copy_item(dst_handle, dst_fs, dst_path, item, force)
        if dst_fs is FilingSystem.AFS:
            dst_handle.flush()


def _collect_copy_items(
    src_handle,
    src_bare: str,
    src_fs: FilingSystem,
    *,
    dst_bare: str,
    dst_slash: bool,
    dst_image: Path,
    dst_fs: FilingSystem,
    recursive: bool,
    src_glob: bool,
) -> list[dict]:
    """Walk the source side once, returning a plan of copy items.

    Each item is either ``{"kind": "mkdir", "dst": path}`` or
    ``{"kind": "file", "dst": path, "data": bytes, "load": int,
    "exec": int, "access": Access}``.  The plan is linear; the
    write phase is free to execute items in order.
    """
    from oaknut.file.access_mapping import access_from_stat

    items: list[dict] = []

    src_is_dfs = src_fs is FilingSystem.DFS

    if src_glob:
        matches = _expand_glob(src_handle, src_bare, src_fs)
        if not matches:
            raise click.ClickException(f"no matches for {src_bare!r}")
        dst_must_be_dir = len(matches) > 1 or any(m.is_dir() for m in matches)
        _check_dst_is_dir(
            dst_image, dst_fs, dst_bare, dst_slash, required=dst_must_be_dir
        )
        if dst_must_be_dir or dst_slash:
            items.append({"kind": "mkdir", "dst": dst_bare})
        for match in matches:
            leaf = match.name
            # DFS "$" globbed as a parent? Flatten onto dst_bare.
            transparent = src_is_dfs and match.is_dir() and leaf == "$"
            sub_dst = dst_bare if transparent else _join(dst_bare, leaf)
            if match.is_dir():
                if not recursive:
                    click.echo(
                        f"skipping directory {match.path}"
                        f" (use -r to copy recursively)",
                        err=True,
                    )
                    continue
                _walk_tree(match, sub_dst, items, src_is_dfs=src_is_dfs)
            else:
                items.append(_file_item(match, sub_dst, access_from_stat(match.stat())))
        if dst_fs is FilingSystem.DFS:
            _validate_dfs_items(items)
        return items

    # Non-glob: single source.
    source = _navigate(src_handle, src_bare, src_fs)
    if not source.exists():
        raise click.ClickException(f"path not found: {src_bare}")

    # Figure out whether the destination should be treated as a
    # target directory (and we copy source "into" it) or as the
    # full target path.
    dst_is_dir_like = dst_slash or _path_is_existing_dir(
        dst_image, dst_fs, dst_bare
    )

    if source.is_dir():
        if not recursive:
            raise click.ClickException(
                f"'{src_bare}' is a directory (use -r to copy recursively)"
            )
        # A source that IS the root (ADFS ``$``, AFS ``$``, or the
        # DFS virtual root whose children are directory letters) is
        # transparent on the copy — there's no sensible subdirectory
        # to wrap it in on the destination; its contents should land
        # at dst_bare directly.  The DFS ``$`` directory behaves the
        # same way because it's the DFS default directory and maps
        # one-for-one onto ADFS ``$`` during round-trip (issue #6).
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
        _walk_tree(source, rel, items, src_is_dfs=src_is_dfs)
        if dst_fs is FilingSystem.DFS:
            _validate_dfs_items(items)
        return items

    # Source is a file.
    if dst_is_dir_like:
        items.append({"kind": "mkdir", "dst": dst_bare})
        rel = _join(dst_bare, source.name)
    else:
        rel = dst_bare
    items.append(_file_item(source, rel, access_from_stat(source.stat())))
    if dst_fs is FilingSystem.DFS:
        _validate_dfs_items(items)
    return items


def _expand_glob(handle, src_bare: str, fs: FilingSystem) -> list:
    """Return children of the literal parent matching the leaf pattern.

    Only the leaf component of ``src_bare`` may contain wildcards;
    the parent directory path is navigated literally.
    """
    parent, leaf_pattern = _split_parent_leaf(src_bare)
    if _has_wildcard(parent):
        raise click.ClickException(
            f"wildcards in directory components are not supported: {src_bare!r}"
        )
    parent_node = _navigate(handle, parent, fs)
    if not parent_node.exists() or not parent_node.is_dir():
        raise click.ClickException(
            f"parent directory of glob does not exist: {parent or '$'!r}"
        )
    return [c for c in parent_node.iterdir() if _match_acorn(leaf_pattern, c.name)]


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
    dir_node, dst_prefix: str, items: list[dict], *, src_is_dfs: bool = False
) -> None:
    """Depth-first walk: record each directory with a mkdir item
    and each file with a file item.

    When the source filesystem is DFS, a child directory named
    ``$`` is treated as transparent — its contents are placed at
    ``dst_prefix`` rather than under a ``$`` subdirectory — so the
    DFS default directory collapses onto the destination root
    during a DFS → ADFS/AFS copy.  DFS's other directory letters
    (A..Z) become subdirectories on the destination as usual.
    """
    from oaknut.file.access_mapping import access_from_stat

    for child in dir_node.iterdir():
        # DFS "$" directory is transparent on the walk — see rule
        # for issue #6 DFS↔ADFS round-trip.
        if src_is_dfs and child.is_dir() and child.name == "$":
            _walk_tree(child, dst_prefix, items, src_is_dfs=src_is_dfs)
            continue
        rel = _join(dst_prefix, child.name)
        if child.is_dir():
            items.append({"kind": "mkdir", "dst": rel})
            _walk_tree(child, rel, items, src_is_dfs=src_is_dfs)
        else:
            items.append(_file_item(child, rel, access_from_stat(child.stat())))


def _file_item(source, rel_dst: str, access) -> dict:
    """Build a ``file`` copy item."""
    return {
        "kind": "file",
        "dst": rel_dst,
        "data": source.read_bytes(),
        "load": getattr(source.stat(), "load_address", 0),
        "exec": getattr(source.stat(), "exec_address", 0),
        "access": access,
    }


def _join(parent: str, leaf: str) -> str:
    if not parent or parent == "$":
        return f"$.{leaf}" if parent == "$" else leaf
    return f"{parent}.{leaf}"


def _path_is_existing_dir(image: Path, fs: FilingSystem, bare: str) -> bool:
    """Is *bare* an existing directory on the destination image?"""
    with open_image(image, fs) as handle:
        node = _navigate(handle, bare, fs)
        return node.exists() and node.is_dir()


def _check_dst_is_dir(
    image: Path, fs: FilingSystem, bare: str, slash: bool, *, required: bool
) -> None:
    """Enforce the "destination must be a directory" rule."""
    if slash:
        return
    if _path_is_existing_dir(image, fs, bare):
        return
    if required:
        raise click.ClickException(
            f"destination {bare!r} must be a directory "
            "(end with '/' or pre-create it) when the source expands "
            "to multiple items or contains directories"
        )


def _ensure_dir_chain(dst_handle, bare: str, fs: FilingSystem) -> None:
    """Create *bare* and any missing parents on the destination.

    DFS is flat — no true subdirectories exist to create.  The call
    is a no-op there; writes later prompt directory-letter
    registration automatically.
    """
    if fs is FilingSystem.DFS:
        return
    if not bare or bare == "$":
        return
    # Normalise to a "$."-prefixed absolute path and walk components.
    trimmed = bare
    if trimmed.startswith("$."):
        trimmed = trimmed[2:]
    elif trimmed == "$":
        return
    cursor = "$"
    for part in trimmed.split("."):
        if not part:
            continue
        cursor = f"{cursor}.{part}"
        node = _navigate(dst_handle, cursor, fs)
        if not node.exists():
            node.mkdir()


def _write_copy_item(
    dst_handle, dst_fs: FilingSystem, dst_path: str, item: dict, force: bool
) -> None:
    """Write a file item to its destination path."""
    from oaknut.file.access_mapping import access_to_write_kwargs

    # Make sure the parent exists for hierarchical destinations.
    # On DFS there are no real directories to create — the letter
    # prefix comes into being implicitly when a file claims it — so
    # we only need the ensure pass on ADFS/AFS.  Paths have already
    # been validated against DFS's shape by the collect stage.
    parent, _leaf = _split_parent_leaf(dst_path)
    if parent and dst_fs is not FilingSystem.DFS:
        _ensure_dir_chain(dst_handle, parent, dst_fs)

    dest = _navigate(dst_handle, dst_path, dst_fs)
    if dest.exists():
        if not force:
            raise click.ClickException(
                f"'{dst_path}' already exists (use -f to overwrite)"
            )
        dest.unlink()

    kwargs: dict = {
        "load_address": item["load"],
        "exec_address": item["exec"],
    }
    kwargs.update(access_to_write_kwargs(item["access"], dst_fs.value))
    dest.write_bytes(item["data"], **kwargs)


_alias("*COPY", "cp")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@click.option("-p", is_flag=True, help="No error if directory already exists.")
def mkdir(image: Path, path: str, p: bool) -> None:
    """Create a directory (ADFS/AFS only). Alias: *CDIR."""
    fs, bare = resolve_path(image, path)
    if fs is FilingSystem.DFS:
        raise click.ClickException("mkdir is not supported for DFS images")
    with open_image(image, fs, mode="r+b") as handle:
        target = _navigate(handle, bare, fs)
        if target.exists():
            if p:
                return
            raise click.ClickException(f"'{bare}' already exists")
        target.mkdir()
        if fs is FilingSystem.AFS:
            handle.flush()


_alias("*CDIR", "mkdir")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@click.argument("access")
@click.option(
    "-r", "--recursive", is_flag=True, help="Recurse into directory matches."
)
@click.option(
    "--dry-run", is_flag=True, help="Print what would change without modifying the image."
)
def chmod(
    image: Path, path: str, access: str, recursive: bool, dry_run: bool
) -> None:
    """Set file access permissions (Acorn alias: *ACCESS).

    ACCESS is symbolic (e.g. LWR/R, WR/WR) or hex (0x0B, 33).
    DFS only supports the L (locked) bit; other flags are ignored.

    PATH may contain Acorn wildcards (``*``, ``#``) to apply the
    same access to every matching file.  ``-r`` recurses into any
    directory match.
    """
    from oaknut.file import Access, parse_access

    flags = parse_access(access)
    fs, bare = resolve_path(image, path)
    mode = "rb" if dry_run else "r+b"
    with open_image(image, fs, mode=mode) as handle:
        for target in _iter_targets(handle, bare, fs, recursive=recursive):
            if dry_run:
                click.echo(f"would chmod {target.path} {access}")
                continue
            if fs is FilingSystem.DFS:
                # DFS only has lock/unlock.
                if flags & Access.L:
                    target.lock()
                else:
                    target.unlock()
            else:
                target.chmod(int(flags))
        if fs is FilingSystem.AFS and not dry_run:
            handle.flush()


_alias("*ACCESS", "chmod")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@click.option(
    "-r", "--recursive", is_flag=True, help="Recurse into directory matches."
)
@click.option(
    "--dry-run", is_flag=True, help="Print what would change without modifying the image."
)
def lock(image: Path, path: str, recursive: bool, dry_run: bool) -> None:
    """Lock a file.  PATH may be a wildcard; ``-r`` recurses."""
    fs, bare = resolve_path(image, path)
    mode = "rb" if dry_run else "r+b"
    with open_image(image, fs, mode=mode) as handle:
        for target in _iter_targets(handle, bare, fs, recursive=recursive):
            if dry_run:
                click.echo(f"would lock {target.path}")
                continue
            target.lock()
        if fs is FilingSystem.AFS and not dry_run:
            handle.flush()


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@click.option(
    "-r", "--recursive", is_flag=True, help="Recurse into directory matches."
)
@click.option(
    "--dry-run", is_flag=True, help="Print what would change without modifying the image."
)
def unlock(image: Path, path: str, recursive: bool, dry_run: bool) -> None:
    """Unlock a file.  PATH may be a wildcard; ``-r`` recurses."""
    fs, bare = resolve_path(image, path)
    mode = "rb" if dry_run else "r+b"
    with open_image(image, fs, mode=mode) as handle:
        for target in _iter_targets(handle, bare, fs, recursive=recursive):
            if dry_run:
                click.echo(f"would unlock {target.path}")
                continue
            target.unlock()
        if fs is FilingSystem.AFS and not dry_run:
            handle.flush()


@cli.command(name="set-load")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@click.argument("addr")
@click.option(
    "-r", "--recursive", is_flag=True, help="Recurse into directory matches."
)
@click.option(
    "--dry-run", is_flag=True, help="Print what would change without modifying the image."
)
def set_load(
    image: Path, path: str, addr: str, recursive: bool, dry_run: bool
) -> None:
    """Set a file's load address.

    PATH may contain Acorn wildcards; ``-r`` recurses into directory
    matches (directories themselves are skipped — they have no load
    address field).
    """
    address = int(addr, 0)
    fs, bare = resolve_path(image, path)
    mode = "rb" if dry_run else "r+b"
    with open_image(image, fs, mode=mode) as handle:
        for target in _iter_targets(handle, bare, fs, recursive=recursive):
            if target.is_dir():
                continue  # load address is meaningless for a directory
            if dry_run:
                click.echo(f"would set-load {target.path} {address:#010x}")
                continue
            target.set_load_address(address)
        if fs is FilingSystem.AFS and not dry_run:
            handle.flush()


@cli.command(name="set-exec")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@click.argument("addr")
@click.option(
    "-r", "--recursive", is_flag=True, help="Recurse into directory matches."
)
@click.option(
    "--dry-run", is_flag=True, help="Print what would change without modifying the image."
)
def set_exec(
    image: Path, path: str, addr: str, recursive: bool, dry_run: bool
) -> None:
    """Set a file's exec address.

    PATH may contain Acorn wildcards; ``-r`` recurses into directory
    matches (directories themselves are skipped — they have no exec
    address field).
    """
    address = int(addr, 0)
    fs, bare = resolve_path(image, path)
    mode = "rb" if dry_run else "r+b"
    with open_image(image, fs, mode=mode) as handle:
        for target in _iter_targets(handle, bare, fs, recursive=recursive):
            if target.is_dir():
                continue
            if dry_run:
                click.echo(f"would set-exec {target.path} {address:#010x}")
                continue
            target.set_exec_address(address)
        if fs is FilingSystem.AFS and not dry_run:
            handle.flush()


@cli.command(name="get-load")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@report_output
def get_load(image: Path, path: str):
    """Print a file's load address."""
    from asyoulikeit.scalar_data import ScalarContent
    from asyoulikeit.tabular_data import Report, Reports

    fs, bare = resolve_path(image, path)
    with open_image(image, fs) as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        st = target.stat()
    return Reports(
        load=Report(
            data=ScalarContent(value=f"{st.load_address:08X}", title="Load"),
        ),
    )


@cli.command(name="get-exec")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@report_output
def get_exec(image: Path, path: str):
    """Print a file's exec address."""
    from asyoulikeit.scalar_data import ScalarContent
    from asyoulikeit.tabular_data import Report, Reports

    fs, bare = resolve_path(image, path)
    with open_image(image, fs) as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        st = target.stat()
    return Reports(
        exec=Report(
            data=ScalarContent(value=f"{st.exec_address:08X}", title="Exec"),
        ),
    )


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("new_title", required=False, default=None)
@report_output
def title(image: Path, new_title: str | None):
    """Read or set disc title (Acorn alias: *TITLE)."""
    from asyoulikeit.scalar_data import ScalarContent
    from asyoulikeit.tabular_data import Report, Reports

    fs = detect_filing_system(image)
    if new_title is None:
        with open_image(image, fs) as handle:
            current = handle.title
        return Reports(
            title=Report(
                data=ScalarContent(value=current, title="Title"),
            ),
        )
    with open_image(image, fs, mode="r+b") as handle:
        handle.title = new_title
    return None


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
@report_output
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
    from oaknut.file import BootOption

    fs = detect_filing_system(image)
    if boot_option is None:
        with open_image(image, fs) as handle:
            bo = BootOption(handle.boot_option)
        return Reports(
            boot_option=Report(
                data=ScalarContent(
                    value=f"{bo.value} ({bo.name})",
                    title="Boot option",
                ),
            ),
        )
    with open_image(image, fs, mode="r+b") as handle:
        handle.boot_option = boot_option
    return None


_alias("*OPT4", "opt")


# ---------------------------------------------------------------------------
# Whole-image operations
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("host_path", type=click.Path(path_type=Path))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(
        ["ssd", "dsd", "adfs-s", "adfs-m", "adfs-l", "adfs-hard"],
        case_sensitive=False,
    ),
    required=True,
    help="Disc image format.",
)
@click.option("--title", "disc_title", default="", help="Disc title.")
@click.option(
    "--capacity",
    default=None,
    help="Capacity (hard disc). Accepts e.g. 10MB, 40MiB, 1024kB, or plain bytes.",
)
def create(host_path: Path, fmt: str, disc_title: str, capacity: str | None) -> None:
    """Create a new empty disc image."""
    if fmt == "ssd":
        from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS

        with DFS.create_file(host_path, ACORN_DFS_80T_SINGLE_SIDED, title=disc_title):
            pass
    elif fmt == "dsd":
        from oaknut.dfs import ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, DFS

        with DFS.create_file(host_path, ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, title=disc_title):
            pass
    elif fmt == "adfs-s":
        from oaknut.adfs import ADFS, ADFS_S

        with ADFS.create_file(host_path, ADFS_S, title=disc_title):
            pass
    elif fmt == "adfs-m":
        from oaknut.adfs import ADFS, ADFS_M

        with ADFS.create_file(host_path, ADFS_M, title=disc_title):
            pass
    elif fmt == "adfs-l":
        from oaknut.adfs import ADFS, ADFS_L

        with ADFS.create_file(host_path, ADFS_L, title=disc_title):
            pass
    elif fmt == "adfs-hard":
        from oaknut.adfs import ADFS
        from oaknut.file.capacity import parse_capacity

        if capacity is None:
            raise click.ClickException("--capacity is required for adfs-hard")
        try:
            capacity_bytes = parse_capacity(capacity)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        with ADFS.create_file(host_path, capacity_bytes=capacity_bytes, title=disc_title):
            pass

    click.echo(f"Created {host_path}")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
def compact(image: Path) -> None:
    """Defragment a disc image, consolidating free space."""
    fs = detect_filing_system(image)
    with open_image(image, fs, mode="r+b") as handle:
        try:
            count = handle.compact()
        except NotImplementedError as exc:
            raise click.ClickException(str(exc))
        click.echo(f"Compacted {count} object(s)")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["ssd", "dsd"], case_sensitive=False),
    default=None,
    help="Target disc format. Inferred from file extension if omitted.",
)
def expand(image: Path, fmt: str | None) -> None:
    """Expand a truncated disc image to its canonical format size.

    Truncated images (e.g. produced by BeebAsm) omit trailing empty
    sectors.  This command appends zero bytes to bring the file up to
    the full format size.
    """
    from oaknut.dfs.dfs import expand as dfs_expand
    from oaknut.dfs.formats import (
        ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
        ACORN_DFS_80T_SINGLE_SIDED,
    )

    if fmt is None:
        ext = image.suffix.lower()
        if ext == ".ssd":
            fmt = "ssd"
        elif ext == ".dsd":
            fmt = "dsd"
        else:
            raise click.ClickException(
                f"Cannot infer format from extension '{image.suffix}'. "
                f"Use --format to specify ssd or dsd."
            )

    if fmt == "ssd":
        disk_format = ACORN_DFS_80T_SINGLE_SIDED
    else:
        disk_format = ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED

    try:
        bytes_added = dfs_expand(image, disk_format)
    except ValueError as exc:
        raise click.ClickException(str(exc))

    if bytes_added == 0:
        click.echo(f"{image.name} is already {disk_format.image_size} bytes")
    else:
        click.echo(f"Expanded {image.name} by {bytes_added} bytes")


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

    fs = detect_filing_system(image)
    host_dir.mkdir(parents=True, exist_ok=True)

    with open_image(image, fs) as handle:
        _export_recursive(handle.root, host_dir, resolved_meta_format, owner, verbose, fs)


def _export_recursive(
    node,
    host_dir: Path,
    meta_format,
    owner: int,
    verbose: bool,
    fs: FilingSystem,
) -> None:
    """Recursively export files from the image to the host directory."""
    from oaknut.file import AcornMeta, export_with_metadata

    for child in node.iterdir():
        if child.is_dir():
            sub_dir = host_dir / child.name
            sub_dir.mkdir(exist_ok=True)
            _export_recursive(child, sub_dir, meta_format, owner, verbose, fs)
        else:
            data = child.read_bytes()
            st = child.stat()
            meta = AcornMeta(
                load_addr=getattr(st, "load_address", None),
                exec_addr=getattr(st, "exec_address", None),
                attr=int(st.access)
                if hasattr(st, "access")
                else (0x08 if getattr(st, "locked", False) else 0),
            )
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
    image: Path, host_dir: Path, meta_format: str | None, verbose: bool,
) -> None:
    """Bulk-import a host directory into the image."""
    from oaknut.file import DEFAULT_IMPORT_META_FORMATS, MetaFormat

    if meta_format is not None and meta_format != "none":
        meta_formats = (MetaFormat(meta_format),)
    else:
        meta_formats = DEFAULT_IMPORT_META_FORMATS

    fs = detect_filing_system(image)
    with open_image(image, fs, mode="r+b") as handle:
        _import_host_dir(handle, handle.root, host_dir, meta_formats, verbose, fs)
        if fs is FilingSystem.AFS:
            handle.flush()


def _import_host_dir(handle, target_dir, host_dir: Path, meta_formats, verbose, fs):
    """Recursively import files from a host directory."""
    for entry in sorted(host_dir.iterdir()):
        if entry.name.startswith("."):
            continue  # Skip hidden files and INF sidecars.
        if entry.suffix.lower() == ".inf":
            continue  # Skip INF sidecar files.
        if entry.is_file():
            # Derive the in-image name from the host filename (strip metadata suffixes).
            leaf = entry.stem if entry.suffix.lower() in (",inf",) else entry.name
            # Strip any filename-encoded suffixes (,xxx or ,load,exec).
            for sep in (",",):
                if sep in leaf:
                    leaf = leaf[: leaf.index(sep)]
            target = target_dir / leaf
            target.import_file(entry, meta_formats=meta_formats)
            if verbose:
                click.echo(target.name, err=True)
        elif entry.is_dir():
            if fs is FilingSystem.DFS:
                # DFS is flat — import files from subdirectories directly.
                _import_host_dir(handle, target_dir, entry, meta_formats, verbose, fs)
            else:
                # ADFS/AFS — create a subdirectory and recurse.
                sub = target_dir / entry.name
                if not sub.exists():
                    sub.mkdir()
                _import_host_dir(handle, sub, entry, meta_formats, verbose, fs)


# ---------------------------------------------------------------------------
# AFS-specific commands
# ---------------------------------------------------------------------------


@cli.command(name="afs-plan")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--cylinders", type=int, default=None,
    help="Proposed AFS region size in cylinders.",
)
@click.option(
    "--compact", is_flag=True, default=False,
    help="Plan with ADFS compaction to maximise AFS space.",
)
@report_output
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
            afs = adfs.afs_partition
            if afs is not None:
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
                    f"{geom['total_sectors']} sectors "
                    f"({geom['total_bytes']:,} bytes)",
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
            pairs.append(
                ("start_cylinder", "Start cylinder", str(existing["start_cylinder"]))
            )
        sections["existing_afs"] = Report(
            data=_kv_table("Existing AFS partition", pairs)
        )
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
        plan_pairs.append(
            ("suggested_command", "Suggested command", document["suggested_command"])
        )
    sections["plan"] = Report(data=_kv_table("Proposed AFS partition", plan_pairs))
    return Reports(sections)


@cli.command(name="afs-init")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option("--disc-name", required=True, help="AFS disc name.")
@click.option(
    "--cylinders", type=int, default=None,
    help="AFS region size in cylinders (default: use existing free space).",
)
@click.option(
    "--compact", is_flag=True, default=False,
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
        "that built-in's quota/password; Syst requires :S."
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

    with ADFS.from_file(image, mode="r+b") as adfs:
        initialise(adfs, spec=spec)

        # Emplace libraries after initialisation so we can report
        # replacements to the user.
        if emplacements:
            from oaknut.afs.libraries import emplace_library

            afs = adfs.afs_partition
            with afs:
                for name in emplacements:
                    try:
                        replaced = emplace_library(afs, name)
                    except (ValueError, FileNotFoundError) as exc:
                        raise click.ClickException(str(exc))
                    if replaced:
                        for fname in replaced:
                            click.echo(f"  replaced $.{name}/{fname}", err=True)

    click.echo(f"Initialised AFS region on {image}")


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


@cli.command(name="afs-users")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@report_output
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
                quota=f"{u.free_space:#010x}",
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
        new_passwords = afs.users.with_added(
            name,
            system=system,
            password=password,
            quota=quota or 0,
        )
        afs._update_passwords_on_disc(new_passwords)
        afs.flush()
    click.echo(f"Added user '{name}'")


@cli.command(name="afs-userdel")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("name")
def afs_userdel(image: Path, name: str) -> None:
    """Remove a user from the AFS passwords file."""
    with open_image_for_afs_write(image) as (adfs, afs):
        new_passwords = afs.users.with_removed(name)
        afs._update_passwords_on_disc(new_passwords)
        afs.flush()
    click.echo(f"Removed user '{name}'")


@cli.command(name="afs-merge")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Source AFS image to merge from.",
)
@click.option("--target-path", default=None, help="Target AFS path for merge root.")
def afs_merge(image: Path, source: Path, target_path: str | None) -> None:
    """Merge a source AFS tree into the target image."""
    from oaknut.adfs import ADFS
    from oaknut.afs import merge

    with ADFS.from_file(image, mode="r+b") as target_adfs:
        target_afs = target_adfs.afs_partition
        if target_afs is None:
            raise click.ClickException("no AFS partition found on target disc")

        with ADFS.from_file(source) as source_adfs:
            source_afs = source_adfs.afs_partition
            if source_afs is None:
                raise click.ClickException("no AFS partition found on source disc")

            target_root = target_afs.root
            if target_path:
                target_root = _navigate_afs(target_afs, target_path)

            merge(target_root, source_afs.root)
            target_afs.flush()

    click.echo(f"Merged {source} into {image}")

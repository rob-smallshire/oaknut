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
def ls(image: Path, path: str | None, show_access_byte: bool) -> None:
    """List directory contents (Acorn alias: *CAT)."""
    from rich.console import Console
    from rich.table import Table

    fs, bare = resolve_path(image, path)
    with open_image(image, fs) as handle:
        target = _navigate(handle, bare, fs)

        if not target.exists() and not target.is_dir():
            raise click.ClickException(f"path not found: {bare or '$'}")

        if target.is_file():
            # Single file — just print its name.
            click.echo(target.name)
            return

        entries = list(target.iterdir())

        # Build title line.
        if fs is FilingSystem.DFS:
            title_str = getattr(handle, "title", "") or ""
            free = getattr(handle, "free_sectors", None)
            fmt_name = "DFS"
        elif fs is FilingSystem.AFS:
            title_str = getattr(handle, "disc_name", "") or ""
            free = getattr(handle, "free_sectors", None)
            fmt_name = "AFS"
        else:
            title_str = getattr(handle, "title", "") or ""
            free = getattr(handle, "free_space", None)
            fmt_name = "ADFS"

        table_title = f"{image.name}"
        if title_str:
            table_title += f" — {title_str}"
        table_title += f" [{fmt_name}]"

        table = Table(title=table_title)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Load", justify="right", style="green", no_wrap=True)
        table.add_column("Exec", justify="right", style="green", no_wrap=True)
        table.add_column("Length", justify="right", no_wrap=True)
        table.add_column("Attr", justify="right", style="yellow", no_wrap=True)
        if show_access_byte:
            table.add_column("Hex", justify="right", style="yellow", no_wrap=True)

        for child in entries:
            if child.is_dir():
                row = [f"{child.name}/", "", "", "", ""]
                if show_access_byte:
                    row.append("")
                table.add_row(*row)
                continue
            st = child.stat()
            load_str = f"{st.load_address:08X}" if hasattr(st, "load_address") else ""
            exec_str = f"{st.exec_address:08X}" if hasattr(st, "exec_address") else ""
            length_str = f"{st.length:08X}" if hasattr(st, "length") else ""
            locked = getattr(st, "locked", False)
            attr_str = "L" if locked else ""
            if hasattr(st, "access"):
                attr_str = _format_access(st.access)
            row = [child.name, load_str, exec_str, length_str, attr_str]
            if show_access_byte:
                row.append(_access_byte_hex(st))
            table.add_row(*row)

        if free is not None:
            if fs is FilingSystem.ADFS:
                table.caption = f"Free: {free:,} bytes"
            else:
                table.caption = f"Free: {free} sectors"

        Console().print(table)


_alias("*CAT", "ls")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path", required=False, default=None)
def tree(image: Path, path: str | None) -> None:
    """Display recursive directory tree."""
    if path is not None:
        # Explicit path (possibly with FS prefix) — show that subtree only.
        fs, bare = resolve_path(image, path)
        with open_image(image, fs) as handle:
            root = _navigate(handle, bare, fs)
            if not root.exists() and not root.is_dir():
                raise click.ClickException(f"path not found: {bare or '$'}")
            click.echo(root.name)
            _print_children(root, "")
    else:
        # No path — show all partitions with image filename as root.
        _tree_whole_image(image)


def _tree_whole_image(image_filepath: Path) -> None:
    """Print a tree of all partitions on the image."""
    detected = detect_filing_system(image_filepath)

    if detected is FilingSystem.DFS:
        with _open_dfs(image_filepath) as handle:
            # DFS root has $ as a child directory.
            click.echo(image_filepath.name)
            _print_children(handle.root, "")
        return

    with _open_adfs(image_filepath) as adfs:
        afs = adfs.afs_partition
        if afs is None:
            # Single ADFS — root ($) is the sole child of the image.
            click.echo(image_filepath.name)
            _print_node(adfs.root, "", True)
        else:
            # Dual partition — ADFS and AFS each contain a $ root.
            click.echo(image_filepath.name)
            _print_labelled_partition("ADFS", adfs.root, "", False)
            _print_labelled_partition("AFS", afs.root, "", True)


def _print_labelled_partition(label: str, root, prefix: str, is_last: bool) -> None:
    """Print a partition label with its $ root underneath."""
    connector = "└── " if is_last else "├── "
    extension = "    " if is_last else "│   "
    click.echo(f"{prefix}{connector}{label}")
    _print_node(root, prefix + extension, True)


def _print_node(node, prefix: str, is_last: bool) -> None:
    """Print a node as a tree child, then recurse into its children."""
    connector = "└── " if is_last else "├── "
    click.echo(f"{prefix}{connector}{node.name}")
    if node.is_dir():
        extension = prefix + ("    " if is_last else "│   ")
        _print_children(node, extension)


def _print_children(node, prefix: str) -> None:
    """Print all children of a directory node."""
    children = list(node.iterdir())
    for i, child in enumerate(children):
        _print_node(child, prefix, i == len(children) - 1)


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path", required=False, default=None)
def stat(image: Path, path: str | None) -> None:
    """Disc summary (no path) or file metadata (with path). Alias: *INFO."""
    fs, bare = resolve_path(image, path)

    if not bare:
        # Whole-disc summary.
        _stat_disc(image, fs)
    else:
        # Single file/directory metadata.
        with open_image(image, fs) as handle:
            target = _navigate(handle, bare, fs)
            if not target.exists():
                raise click.ClickException(f"path not found: {bare}")
            st = target.stat()
            click.echo(f"Name:    {target.name}")
            if hasattr(st, "load_address"):
                click.echo(f"Load:    {st.load_address:08X}")
            if hasattr(st, "exec_address"):
                click.echo(f"Exec:    {st.exec_address:08X}")
            if hasattr(st, "length"):
                click.echo(f"Length:  {st.length:08X}")
            locked = getattr(st, "locked", False)
            if hasattr(st, "access"):
                click.echo(f"Attr:    {_format_access(st.access)}")
            elif locked:
                click.echo("Attr:    L")
            if hasattr(st, "is_directory"):
                click.echo(f"Dir:     {st.is_directory}")


_alias("*INFO", "stat")


_SECTOR_SIZE = 256


def _stat_disc(image_filepath: Path, fs: FilingSystem) -> None:
    """Print whole-disc summary as a Rich panel.

    For a no-prefix invocation the layout is a disc-level header (physical
    geometry + total size, both derived from the geometry so they stay
    self-consistent — see issue #7) followed by one ``Partition N: <FS>``
    block per filing-system partition on the image.

    When the user scopes the view with an ``afs:`` prefix, ``fs`` is
    :data:`FilingSystem.AFS` and a flat partition-only block is shown
    instead — the prefix is a deliberate single-partition drill-down.
    """
    from rich.console import Console
    from rich.panel import Panel

    with open_image(image_filepath, fs) as handle:
        lines: list[str] = []
        if fs is FilingSystem.AFS:
            _append_afs_partition_only(lines, handle)
        elif fs is FilingSystem.DFS:
            _append_disc_header_dfs(lines, handle)
            lines.append("")
            lines.append("Partition 1: DFS")
            _append_dfs_partition(lines, handle)
        else:
            _append_disc_header_adfs(lines, handle)
            lines.append("")
            lines.append("Partition 1: ADFS")
            _append_adfs_partition(lines, handle)
            afs = handle.afs_partition
            if afs is not None:
                lines.append("")
                lines.append("Partition 2: AFS")
                _append_afs_partition(lines, handle, afs)

        Console().print(Panel("\n".join(lines), title=str(image_filepath.name)))


def _format_size(sectors: int) -> str:
    """Consistent ``X bytes (Y sectors)`` rendering."""
    return f"{sectors * _SECTOR_SIZE:,} bytes ({sectors} sectors)"


def _append_disc_header_dfs(lines: list[str], handle) -> None:
    """Disc-level block for DFS: total sectors only (no C/H/S decomposition)."""
    total_sectors = handle.info["total_sectors"]
    lines.append("Disc")
    lines.append(f"  Size:         {_format_size(total_sectors)}")


def _append_disc_header_adfs(lines: list[str], handle) -> None:
    """Disc-level block for ADFS: geometry + physical disc size.

    Both figures come from ``handle.geometry`` so the byte count and
    sector count agree with each other and with the image file size
    on disc (issue #7).
    """
    geom = handle.geometry
    total_sectors = geom.cylinders * geom.heads * geom.sectors_per_track
    lines.append("Disc")
    lines.append(
        f"  Geometry:     {geom.cylinders} cylinders, "
        f"{geom.heads} heads, {geom.sectors_per_track} sectors/track"
    )
    lines.append(f"  Size:         {_format_size(total_sectors)}")


def _append_dfs_partition(lines: list[str], handle) -> None:
    from oaknut.file import BootOption

    info = handle.info
    lines.append(f"  Title:        {handle.title}")
    boot = BootOption(handle.boot_option)
    lines.append(f"  Boot option:  {boot.name} ({boot.value})")
    lines.append(f"  Size:         {_format_size(info['total_sectors'])}")
    lines.append(f"  Free:         {_format_size(info['free_sectors'])}")
    lines.append(f"  Files:        {info['num_files']}")


def _append_adfs_partition(lines: list[str], handle) -> None:
    """ADFS partition block.

    ``handle.total_size`` reflects any AFS-driven ``shrink_to`` that
    has happened, so the partition's cylinder range and size are
    correct whether the disc is whole-ADFS or split with AFS.
    """
    from oaknut.file import BootOption

    geom = handle.geometry
    adfs_sectors = handle.total_size // _SECTOR_SIZE
    adfs_cylinders = adfs_sectors // (geom.heads * geom.sectors_per_track)
    lines.append(f"  Title:        {handle.title}")
    boot = BootOption(handle.boot_option)
    lines.append(f"  Boot option:  {boot.name} ({boot.value})")
    if adfs_cylinders < geom.cylinders:
        # Only worth showing the cylinder range when it isn't the
        # whole disc — otherwise it's just noise.
        lines.append(
            f"  Range:        cylinders 0-{adfs_cylinders - 1}"
        )
    lines.append(f"  Size:         {_format_size(adfs_sectors)}")
    free_sectors = handle.free_space // _SECTOR_SIZE
    lines.append(f"  Free:         {_format_size(free_sectors)}")


def _append_afs_partition(lines: list[str], adfs_handle, afs) -> None:
    """AFS partition block beneath its containing ADFS disc.

    Cylinder range is derived from the info sector's start cylinder
    and the physical disc geometry.  User list is intentionally
    omitted — it can be arbitrarily long and a separate concern (see
    ``disc afs-users``).
    """
    geom = adfs_handle.geometry
    afs_cylinders = geom.cylinders - afs.start_cylinder
    afs_sectors = afs_cylinders * geom.heads * geom.sectors_per_track
    lines.append(f"  Disc name:    {afs.disc_name}")
    lines.append(
        f"  Range:        cylinders {afs.start_cylinder}-{geom.cylinders - 1}"
    )
    lines.append(f"  Size:         {_format_size(afs_sectors)}")
    lines.append(f"  Free:         {_format_size(afs.free_sectors)}")


def _append_afs_partition_only(lines: list[str], handle) -> None:
    """Flat AFS-scoped view (``disc stat image afs:``)."""
    geom = handle.geometry
    lines.append(f"Disc name:      {handle.disc_name}")
    lines.append(f"Start cylinder: {handle.start_cylinder}")
    lines.append(f"Cylinders:      {geom.cylinders}")
    lines.append(f"Sectors/cyl:    {geom.sectors_per_cylinder}")
    lines.append(f"Total sectors:  {geom.total_sectors}")
    lines.append(f"Free sectors:   {handle.free_sectors}")


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
def find(image: Path, pattern: str) -> None:
    """Find files matching an Acorn wildcard pattern."""
    fs, bare = resolve_path(image, pattern)
    # For find, the "bare" part is the pattern, not a path to navigate to.
    # We walk the whole image and match against the pattern.
    with open_image(image, fs) as handle:
        _find_recursive(handle.root, bare, fs)


def _match_acorn_wildcard(pattern: str, name: str) -> bool:
    """Match a name against an Acorn-style wildcard pattern.

    ``*`` matches any sequence, ``?`` matches one character.
    Case-insensitive to match Acorn convention.
    """
    import fnmatch

    # Acorn wildcards use the same semantics as fnmatch.
    return fnmatch.fnmatch(name.upper(), pattern.upper())


def _find_recursive(node, pattern: str, fs: FilingSystem) -> None:
    """Walk a directory tree, printing paths matching *pattern*."""
    # The pattern may include directory components separated by '.'
    # For simplicity, match against full Acorn path and leaf name.
    for child in node.iterdir():
        name = child.name
        path_str = getattr(child, "path", name)
        if _match_acorn_wildcard(pattern, name) or _match_acorn_wildcard(pattern, path_str):
            click.echo(path_str)
        if child.is_dir():
            _find_recursive(child, pattern, fs)


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
    """Delete file(s) from the image (Acorn alias: *DELETE)."""
    fs_type = detect_filing_system(image)
    first_prefix = None
    targets: list[tuple[FilingSystem, str]] = []
    for p in paths:
        fs, bare = resolve_path(image, p)
        if first_prefix is None:
            first_prefix = fs
        targets.append((fs, bare))

    mode = "rb" if dry_run else "r+b"
    with open_image(image, first_prefix or fs_type, mode=mode) as handle:
        for fs, bare in targets:
            target = _navigate(handle, bare, fs)
            if not target.exists():
                if force:
                    continue
                raise click.ClickException(f"path not found: {bare}")
            if target.is_dir() and not recursive:
                raise click.ClickException(
                    f"'{bare}' is a directory (use -r to remove recursively)"
                )
            if dry_run:
                click.echo(f"would remove: {bare}")
                continue

            # Handle locked files with --force.
            try:
                target.unlink()
            except Exception as exc:
                if force and "locked" in str(exc).lower():
                    if hasattr(target, "unlock"):
                        target.unlock()
                    target.unlink()
                else:
                    raise click.ClickException(str(exc))

        if fs == FilingSystem.AFS and not dry_run:
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
def cp(args: tuple[str, ...], force: bool) -> None:
    """Copy a file within or between disc images (Acorn alias: *COPY).

    \b
    Colon syntax (preferred for cross-image):
      disc cp source.ssd:$.HELLO target.dat:$.HELLO

    \b
    Three-arg form (within one image):
      disc cp IMAGE SRC DST

    Copies across DFS, ADFS, and AFS in any combination. Load and
    exec addresses are preserved; access attributes are mapped
    best-effort (DFS only has the locked bit).
    """
    from .cli_paths import parse_image_path

    if len(args) == 2:
        src_parsed = parse_image_path(args[0])
        dst_parsed = parse_image_path(args[1])
        if src_parsed is not None and dst_parsed is not None:
            # Both use colon syntax: cross-image (or same image).
            _cp_cross_image(src_parsed[0], src_parsed[1], dst_parsed[1], dst_parsed[0], force)
            return
        if src_parsed is not None or dst_parsed is not None:
            raise click.ClickException(
                "when using image:path syntax, both source and destination must use it"
            )
        # Neither has colons — ambiguous with two args.
        raise click.ClickException(
            "cp requires either image:path colon syntax or three arguments (IMAGE SRC DST)"
        )
    elif len(args) == 3:
        # Classic three-arg form: IMAGE SRC DST (within one image).
        image = Path(args[0])
        if not image.is_file():
            raise click.ClickException(f"image not found: {args[0]}")
        _cp_within_image(image, args[1], args[2], force)
    else:
        raise click.ClickException(
            "cp takes 2 arguments (image:path image:path) or 3 (IMAGE SRC DST)"
        )


def _cp_within_image(image: Path, src: str, dst: str, force: bool) -> None:
    """Copy a file within a single disc image."""
    from oaknut.file import copy_file

    fs, bare_src = resolve_path(image, src)
    _, bare_dst = parse_prefix(dst)

    with open_image(image, fs, mode="r+b") as handle:
        source = _navigate(handle, bare_src, fs)
        if not source.exists():
            raise click.ClickException(f"path not found: {bare_src}")
        if source.is_dir():
            raise click.ClickException("directory copy not yet implemented")
        dest = _navigate(handle, bare_dst, fs)
        if dest.exists() and not force:
            raise click.ClickException(f"'{bare_dst}' already exists (use -f to overwrite)")
        if dest.exists() and force:
            dest.unlink()
        copy_file(source, dest, target_fs=fs.value)
        if fs is FilingSystem.AFS:
            handle.flush()


def _cp_cross_image(
    src_image: Path, src: str, dst: str, dst_image: Path, force: bool,
) -> None:
    """Copy a file between two disc images (possibly different formats)."""
    from oaknut.file.access_mapping import access_from_stat, access_to_write_kwargs

    src_fs, src_bare = resolve_path(src_image, src)
    dst_fs, dst_bare = resolve_path(dst_image, dst)

    # Read source data and metadata while the source image is open.
    with open_image(src_image, src_fs) as src_handle:
        source = _navigate(src_handle, src_bare, src_fs)
        if not source.exists():
            raise click.ClickException(f"path not found: {src_bare}")
        if source.is_dir():
            raise click.ClickException("directory copy not yet implemented")
        data = source.read_bytes()
        st = source.stat()
        access = access_from_stat(st)

    # Write to destination with mapped access attributes.
    kwargs = {
        "load_address": getattr(st, "load_address", 0),
        "exec_address": getattr(st, "exec_address", 0),
    }
    kwargs.update(access_to_write_kwargs(access, dst_fs.value))

    with open_image(dst_image, dst_fs, mode="r+b") as dst_handle:
        dest = _navigate(dst_handle, dst_bare, dst_fs)
        if dest.exists() and not force:
            raise click.ClickException(f"'{dst_bare}' already exists (use -f to overwrite)")
        if dest.exists() and force:
            dest.unlink()
        dest.write_bytes(data, **kwargs)
        if dst_fs is FilingSystem.AFS:
            dst_handle.flush()


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
def chmod(image: Path, path: str, access: str) -> None:
    """Set file access permissions (Acorn alias: *ACCESS).

    ACCESS is symbolic (e.g. LWR/R, WR/WR) or hex (0x0B, 33).
    DFS only supports the L (locked) bit; other flags are ignored.
    """
    from oaknut.file import Access, parse_access

    flags = parse_access(access)
    fs, bare = resolve_path(image, path)
    with open_image(image, fs, mode="r+b") as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        if fs is FilingSystem.DFS:
            # DFS only has lock/unlock.
            if flags & Access.L:
                target.lock()
            else:
                target.unlock()
        else:
            target.chmod(int(flags))
            if fs is FilingSystem.AFS:
                handle.flush()


_alias("*ACCESS", "chmod")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
def lock(image: Path, path: str) -> None:
    """Lock a file."""
    fs, bare = resolve_path(image, path)
    with open_image(image, fs, mode="r+b") as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        target.lock()
        if fs is FilingSystem.AFS:
            handle.flush()


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
def unlock(image: Path, path: str) -> None:
    """Unlock a file."""
    fs, bare = resolve_path(image, path)
    with open_image(image, fs, mode="r+b") as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        target.unlock()
        if fs is FilingSystem.AFS:
            handle.flush()


@cli.command(name="set-load")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@click.argument("addr")
def set_load(image: Path, path: str, addr: str) -> None:
    """Set a file's load address."""
    address = int(addr, 0)
    fs, bare = resolve_path(image, path)
    with open_image(image, fs, mode="r+b") as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        target.set_load_address(address)
        if fs is FilingSystem.AFS:
            handle.flush()


@cli.command(name="set-exec")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
@click.argument("addr")
def set_exec(image: Path, path: str, addr: str) -> None:
    """Set a file's exec address."""
    address = int(addr, 0)
    fs, bare = resolve_path(image, path)
    with open_image(image, fs, mode="r+b") as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        target.set_exec_address(address)
        if fs is FilingSystem.AFS:
            handle.flush()


@cli.command(name="get-load")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
def get_load(image: Path, path: str) -> None:
    """Print a file's load address."""
    fs, bare = resolve_path(image, path)
    with open_image(image, fs) as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        st = target.stat()
        click.echo(f"{st.load_address:08X}")


@cli.command(name="get-exec")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("path")
def get_exec(image: Path, path: str) -> None:
    """Print a file's exec address."""
    fs, bare = resolve_path(image, path)
    with open_image(image, fs) as handle:
        target = _navigate(handle, bare, fs)
        if not target.exists():
            raise click.ClickException(f"path not found: {bare}")
        st = target.stat()
        click.echo(f"{st.exec_address:08X}")


@cli.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("new_title", required=False, default=None)
def title(image: Path, new_title: str | None) -> None:
    """Read or set disc title (Acorn alias: *TITLE)."""
    fs = detect_filing_system(image)
    if new_title is None:
        with open_image(image, fs) as handle:
            click.echo(handle.title)
    else:
        with open_image(image, fs, mode="r+b") as handle:
            handle.title = new_title


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
def opt(image: Path, boot_option: int | None) -> None:
    """Read or set boot option (Acorn alias: *OPT4).

    Omit BOOT_OPTION to report the current setting.

    \b
    Values:
      0 / OFF   No action
      1 / LOAD  *LOAD $.!BOOT
      2 / RUN   *RUN $.!BOOT
      3 / EXEC  *EXEC $.!BOOT
    """
    from oaknut.file import BootOption

    fs = detect_filing_system(image)
    if boot_option is None:
        with open_image(image, fs) as handle:
            bo = BootOption(handle.boot_option)
            click.echo(f"{bo.value} ({bo.name})")
    else:
        with open_image(image, fs, mode="r+b") as handle:
            handle.boot_option = boot_option


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


#: Valid values for --as across commands. Extend as new renderers land.
_OUTPUT_FORMATS = ("text", "json")


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
@click.option(
    "--as", "output_format",
    type=click.Choice(_OUTPUT_FORMATS),
    default="text",
    help="Output format (default: text).",
)
def afs_plan(
    image: Path,
    cylinders: int | None,
    compact: bool,
    output_format: str,
) -> None:
    """Show what afs-init would do, without modifying the image.

    By default, plans using the existing tail free extent (matching
    WFSINIT behaviour). With --compact, plans a compaction-first
    layout that reclaims the maximum space. With --cylinders N,
    shows the plan for that specific size. Reports disc geometry,
    current ADFS occupancy, whether compaction is needed, and the
    resulting partition layout.

    Use ``--as json`` to emit a machine-readable document instead
    of the human-readable text report.
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
            _render_afs_plan(document, output_format)
            return

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

        _render_afs_plan(document, output_format)


def _render_afs_plan(document: dict, output_format: str) -> None:
    """Render an afs-plan document in the requested format."""
    if output_format == "json":
        import json
        click.echo(json.dumps(document, indent=2))
        return

    # Default: human-readable text.
    geom = document["geometry"]
    adfs_state = document["adfs"]
    click.echo("Disc geometry")
    click.echo(
        f"  {geom['cylinders']} cylinders, {geom['heads']} heads, "
        f"{geom['sectors_per_track']} sectors/track"
    )
    click.echo(
        f"  {geom['total_sectors']} total sectors ({geom['cylinders']} cylinders)"
    )
    click.echo(
        f"  {adfs_state['used_sectors']} used sectors, "
        f"{adfs_state['free_sectors']} free sectors "
        f"({adfs_state['free_bytes']:,} bytes)"
    )
    click.echo()

    existing = document["existing_afs"]
    if existing["present"]:
        click.echo("This disc already has an AFS partition.")
        if "disc_name" in existing:
            click.echo(
                f"  AFS disc name: {existing['disc_name']}, "
                f"start cylinder: {existing['start_cylinder']}"
            )
        return

    p = document["plan"]
    click.echo("Proposed AFS partition")
    click.echo(
        f"  AFS region:     {p['afs_cylinders']} cylinders "
        f"({p['total_afs_sectors']} sectors, {p['total_afs_bytes']:,} bytes)"
    )
    click.echo(f"  Start cylinder: {p['start_cylinder']}")
    click.echo(f"  ADFS retained:  {p['new_adfs_cylinders']} cylinders")
    click.echo(
        f"  Compaction:     {'required' if p['will_compact'] else 'not required'}"
    )

    if "suggested_command" in document:
        click.echo()
        click.echo(f"To proceed: {document['suggested_command']}")


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
def afs_users(image: Path) -> None:
    """List AFS users with quota and flags."""
    with _open_afs(image) as afs:
        for u in afs.users.active:
            flag = "S" if u.is_system else " "
            click.echo(f"{flag} {u.full_id:20s} quota={u.free_space:#010x}")


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

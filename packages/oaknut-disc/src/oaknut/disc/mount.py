"""Resolve a ``COMPOUND_PATH`` to a mounted partition — the CLI's open path.

Every command routes through :func:`resolve_mount` instead of opening a
specific filing system. It identifies the image by content (via the
``oaknut.filesystem`` coordinator), selects the addressed partition, and
returns a :class:`~oaknut.filesystem.Mount` plus the in-partition path —
importing and branching on no concrete filesystem. A path prefix selects
a *partition* (``afs:``, ``afs.1:``), never a format; ``--filesystem`` /
``--geometry`` force the interpretation.

The mount is currently read-only: the filesystem adapters open over a
private copy of the image bytes, so writes do not persist. Write-back is
added when the mutating commands are migrated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import click
from oaknut.filesystem import (
    Geometry,
    Identification,
    Mount,
    Partition,
    create_filesystem,
    filesystem_names,
    geometry_from_dsc,
    identify,
    reader_for,
    region_reader,
)
from oaknut.filesystem.exceptions import GeometryError

from .cli_paths import parse_compound_path

# A partition selector is a lower-case filesystem key, optionally with a
# ``.N`` index, followed by a colon: ``afs:``, ``afs.1:``, ``acorn-dfs:``.
# Acorn in-partition paths start with ``$``, ``^`` or an upper-case
# directory letter, so they never match — keeping the two unambiguous.
_SELECTOR_RE = re.compile(r"^([a-z][a-z0-9-]*(?:\.\d+)?):(.*)$", re.DOTALL)


@dataclass(frozen=True)
class ResolvedMount:
    """A mounted partition and the path addressed within it.

    For a writable mount the underlying reader (a live, file-backed
    mapping) must stay open while the mount is used, so use this as a
    context manager — ``with resolve_mount(spec, writable=True) as rm:``
    — to release the mapping (and flush the OS write-back) on exit. A
    read-only mount holds a private copy, so closing is a harmless no-op.
    """

    mount: Mount
    path: str
    filesystem: str
    partition: str
    image: Path
    _reader: object = None

    def close(self) -> None:
        # Order matters: the mount borrows a memoryview over the reader's
        # backing store, so it must release that borrow (close the mount)
        # before the reader closes the mmap — an mmap cannot close while a
        # view it exported is still alive.
        mount_close = getattr(self.mount, "close", None)
        if callable(mount_close):
            mount_close()
        if self._reader is not None:
            self._reader.close()

    def __enter__(self) -> "ResolvedMount":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def split_selector(inner_path: str) -> tuple[str | None, str]:
    """Split a leading ``partition:`` selector from an inner path."""
    match = _SELECTOR_RE.match(inner_path)
    if match is None:
        return None, inner_path
    return match.group(1), match.group(2)


def resolve_mount(
    compound_path: str,
    *,
    writable: bool = False,
    force_filesystem: str | None = None,
    force_geometry: str | None = None,
) -> ResolvedMount:
    """Resolve *compound_path* to a mounted partition and in-partition path.

    Identifies the image by content and mounts the selected partition.
    *force_filesystem* / *force_geometry* override detection. With
    *writable* the image is opened for writing and the mount's mutations
    reach the file; the returned :class:`ResolvedMount` then owns a live
    mapping and must be used as a context manager so it is released. A
    read-only mount holds a private copy, so the reader is closed at once.
    """
    outer_filepath, inner_path = parse_compound_path(compound_path)
    selector, in_path = split_selector(inner_path)

    reader = reader_for(outer_filepath, writable=writable)
    try:
        if force_filesystem is not None:
            filesystem = create_filesystem(force_filesystem)
            proposed = filesystem.probe(reader)
            geometry = _geometry(
                filesystem, force_geometry, proposed.geometry if proposed else None
            )
            if geometry is None:
                geometry = _geometry_from_sidecar(outer_filepath)
            if geometry is None:
                # Forcing means "open it as this even though detection
                # declined"; with no proposed, sidecar or explicit
                # geometry, fall back to the filesystem's default for the
                # extension (.ssd → 80T SS, .adl → ADFS-L, …) so an
                # unrecognised but well-shaped image still opens.
                geometry = filesystem.default_geometry(outer_filepath.suffix.lower())
            if geometry is None:
                raise click.ClickException(
                    f"cannot determine geometry for {force_filesystem} from "
                    f"{outer_filepath.name!r}; pass --geometry "
                    f"(run `disc describe-filesystem {force_filesystem}` for options)"
                )
            ambiguities = _ambiguities(force_geometry, proposed)
            surface, geometry, in_path = filesystem.split_volume(in_path, geometry, ambiguities)
            mount = filesystem.open(reader, geometry, surface=surface)
            chosen_name = partition_name = force_filesystem
        else:
            candidates = identify(outer_filepath)
            if not candidates:
                raise click.ClickException(_unrecognised_message(outer_filepath.name))
            host = candidates[0]
            chosen, region = _select(host, selector)
            filesystem = create_filesystem(chosen.filesystem)
            if region is None:
                region_view = reader
            else:
                # A reserved region is a logical-sector run of the host;
                # read it through the host geometry (a window on a linear
                # host, de-interleaved on a floppy).
                region_view = region_reader(
                    reader, host.geometry, region.start_sector, region.num_sectors
                )
            geometry = _geometry(filesystem, force_geometry, chosen.geometry)
            if geometry is None and region is None:
                # The whole-image host's geometry — a hard disc records its
                # CHS only in the .dsc sidecar, not the content. (A reserved
                # partition reads geometry from its own on-disc structure.)
                geometry = _geometry_from_sidecar(outer_filepath)
            # The filesystem peels any leading volume designation (a DFS
            # drive) from the path, choosing the surface and — when a
            # non-zero drive disambiguates a length collision — the geometry.
            # Precedence is explicit --geometry > drive-implied > proposed:
            # a forced geometry is pinned, so no ambiguities are offered.
            ambiguities = _ambiguities(force_geometry, chosen)
            surface, geometry, in_path = filesystem.split_volume(in_path, geometry, ambiguities)
            mount = filesystem.open(region_view, geometry, surface=surface)
            chosen_name = chosen.filesystem
            partition_name = chosen.partition.selector
    except BaseException:
        reader.close()
        raise

    if not writable:
        # The mount holds a private copy; the mapping is no longer needed.
        reader.close()
        return ResolvedMount(mount, in_path, chosen_name, partition_name, outer_filepath)
    # A writable mount maps the file live; keep the reader open until the
    # caller closes the ResolvedMount.
    return ResolvedMount(
        mount, in_path, chosen_name, partition_name, outer_filepath, _reader=reader
    )


def partition_selectors(outer_filepath: Path) -> list[str]:
    """Selectors of every identified partition in *outer_filepath*.

    The host partition first, then each identified contained partition
    (``adfs``, ``afs``, ``afs.1`` …) — the names a prefix would address.
    Raises if nothing recognises the image.
    """
    candidates = identify(outer_filepath)
    if not candidates:
        raise click.ClickException(_unrecognised_message(outer_filepath.name))
    host = candidates[0]
    return [host.partition.selector] + [
        c.partition.selector for c in host.contained if c.identified
    ]


def partition_volumes(outer_filepath: Path, selector: str | None = None) -> list:
    """The independently-addressable volumes within a partition.

    Identifies the image, selects the partition (the host by default),
    and asks its filesystem to enumerate its volumes. A double-sided DFS
    disc reports two (designated ``:0`` / ``:2``); everything else reports
    a single, undesignated volume. Used by ``disc stat`` to list each
    side of a DSD under the designation that addresses it.
    """
    candidates = identify(outer_filepath)
    if not candidates:
        raise click.ClickException(_unrecognised_message(outer_filepath.name))
    host = candidates[0]
    chosen, _region = _select(host, selector)
    filesystem = create_filesystem(chosen.filesystem)
    return list(filesystem.volumes(chosen.geometry))


def _select(best: Identification, selector: str | None) -> tuple[Identification, Partition | None]:
    """Pick the addressed partition from the best candidate's tree.

    Returns ``(identification, region)`` where *region* is ``None`` for
    the whole-image (host) partition, or the reserved-region partition to
    window into. A ``None`` *selector* takes the host.
    """
    if selector is None or selector == best.partition.selector:
        return best, None
    for contained in best.contained:
        if contained.identified and contained.partition.selector == selector:
            return contained, contained.partition
    available = [best.partition.selector] + [
        c.partition.selector for c in best.contained if c.identified
    ]
    raise click.ClickException(f"no such partition {selector!r}; available: {', '.join(available)}")


def _geometry(filesystem, force_geometry: str | None, proposed: Geometry | None):
    """The geometry to open with: forced spec, else the proposed one."""
    if force_geometry is None:
        return proposed
    return filesystem.geometry_grammar().parse(force_geometry)


def _ambiguities(force_geometry: str | None, identification) -> tuple[Geometry, ...]:
    """Geometry ambiguities to offer ``split_volume``, honouring precedence.

    A forced ``--geometry`` pins the layout, so none are offered and a
    drive token inconsistent with it errors. Otherwise the identification's
    own ambiguities are offered, so a non-zero drive may *imply* the
    double-sided reading of a length-ambiguous image.
    """
    if force_geometry is not None or identification is None:
        return ()
    return identification.ambiguities


def _geometry_from_sidecar(outer_filepath: Path) -> Geometry | None:
    """The CHS geometry from an adjacent ``.dsc`` sidecar, if present.

    A hard-disc image records its geometry only in the sidecar, so this
    is geometry *resolution* (a separate layer) — identification stays
    content-first. A malformed sidecar is ignored.
    """
    sidecar = outer_filepath.with_suffix(".dsc")
    if not sidecar.is_file():
        return None
    try:
        return geometry_from_dsc(sidecar.read_bytes())
    except (GeometryError, OSError):
        return None


def _unrecognised_message(name: str) -> str:
    installed = ", ".join(sorted(filesystem_names())) or "(none)"
    return (
        f"no installed filesystem recognises '{name}'. "
        f"Installed filesystems: {installed}. "
        f"Force one with --filesystem if you know what it is."
    )

"""Resolve a ``FILE_SPEC`` to a mounted partition — the CLI's open path.

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
    identify,
    reader_for,
    region_reader,
)

from .cli_paths import parse_file_spec

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
        if self._reader is not None:
            self._reader.close()

    def __enter__(self) -> "ResolvedMount":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def split_selector(in_image_path: str) -> tuple[str | None, str]:
    """Split a leading ``partition:`` selector from an in-image path."""
    match = _SELECTOR_RE.match(in_image_path)
    if match is None:
        return None, in_image_path
    return match.group(1), match.group(2)


def resolve_mount(
    file_spec: str,
    *,
    writable: bool = False,
    force_filesystem: str | None = None,
    force_geometry: str | None = None,
) -> ResolvedMount:
    """Resolve *file_spec* to a mounted partition and in-partition path.

    Identifies the image by content and mounts the selected partition.
    *force_filesystem* / *force_geometry* override detection. With
    *writable* the image is opened for writing and the mount's mutations
    reach the file; the returned :class:`ResolvedMount` then owns a live
    mapping and must be used as a context manager so it is released. A
    read-only mount holds a private copy, so the reader is closed at once.
    """
    image_filepath, in_image_path = parse_file_spec(file_spec)
    selector, in_path = split_selector(in_image_path)

    reader = reader_for(image_filepath, writable=writable)
    try:
        if force_filesystem is not None:
            filesystem = create_filesystem(force_filesystem)
            proposed = filesystem.probe(reader)
            geometry = _geometry(
                filesystem, force_geometry, proposed.geometry if proposed else None
            )
            mount = filesystem.open(reader, geometry)
            chosen_name = partition_name = force_filesystem
        else:
            candidates = identify(image_filepath)
            if not candidates:
                raise click.ClickException(_unrecognised_message(image_filepath.name))
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
            mount = filesystem.open(region_view, geometry)
            chosen_name = chosen.filesystem
            partition_name = chosen.partition.selector
    except BaseException:
        reader.close()
        raise

    if not writable:
        # The mount holds a private copy; the mapping is no longer needed.
        reader.close()
        return ResolvedMount(mount, in_path, chosen_name, partition_name, image_filepath)
    # A writable mount maps the file live; keep the reader open until the
    # caller closes the ResolvedMount.
    return ResolvedMount(
        mount, in_path, chosen_name, partition_name, image_filepath, _reader=reader
    )


def partition_selectors(image_filepath: Path) -> list[str]:
    """Selectors of every identified partition in *image_filepath*.

    The host partition first, then each identified contained partition
    (``adfs``, ``afs``, ``afs.1`` …) — the names a prefix would address.
    Raises if nothing recognises the image.
    """
    candidates = identify(image_filepath)
    if not candidates:
        raise click.ClickException(_unrecognised_message(image_filepath.name))
    host = candidates[0]
    return [host.partition.selector] + [
        c.partition.selector for c in host.contained if c.identified
    ]


def _select(
    best: Identification, selector: str | None
) -> tuple[Identification, Partition | None]:
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
    raise click.ClickException(
        f"no such partition {selector!r}; available: {', '.join(available)}"
    )


def _geometry(filesystem, force_geometry: str | None, proposed: Geometry | None):
    """The geometry to open with: forced spec, else the proposed one."""
    if force_geometry is None:
        return proposed
    return filesystem.geometry_grammar().parse(force_geometry)


def _unrecognised_message(name: str) -> str:
    installed = ", ".join(sorted(filesystem_names())) or "(none)"
    return (
        f"no installed filesystem recognises '{name}'. "
        f"Installed filesystems: {installed}. "
        f"Force one with --filesystem if you know what it is."
    )

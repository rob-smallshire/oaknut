"""The identification cascade: run every registered filesystem, recurse, rank.

:func:`identify` probes an image with every filesystem on the
``oaknut.filesystem`` axis, recurses into the regions a host filesystem
reserves (an ADFS tail), and returns the candidates for the whole image
ranked best-first — each carrying its recursively-identified
``contained`` partitions. It depends on no concrete filesystem package;
discovery is purely by entry point, so any subset can be installed.
"""

from __future__ import annotations

from dataclasses import replace

import stevedore
from oaknut.discimage import BYTES_PER_SECTOR
from oaknut.extension import (
    create_extension,
    describe_extension,
    list_extensions,
    load_failure_callback,
)
from oaknut.filesystem.exceptions import FilesystemExtensionError
from oaknut.filesystem.filesystem import (
    FILESYSTEM_KIND,
    FILESYSTEM_NAMESPACE,
    Filesystem,
)
from oaknut.filesystem.geometry import Geometry, region_reader
from oaknut.filesystem.identification import (
    Confidence,
    Identification,
    Partition,
    Rejection,
    Survey,
)
from oaknut.filesystem.reader import ImageReader, ImageSource, reader_for

__all__ = [
    "identify",
    "filesystem_names",
    "describe_filesystem",
    "create_filesystem",
    "creating_filesystem",
]


def filesystem_names() -> list[str]:
    """The entry-point names of every registered filesystem."""
    return list_extensions(FILESYSTEM_NAMESPACE)


def describe_filesystem(name: str, *, single_line: bool = False) -> str:
    """The description of one filesystem (its class docstring)."""
    return describe_extension(
        FILESYSTEM_KIND,
        FILESYSTEM_NAMESPACE,
        name,
        FilesystemExtensionError,
        single_line=single_line,
    )


def create_filesystem(name: str) -> Filesystem:
    """Instantiate one filesystem by name."""
    return create_extension(
        kind=FILESYSTEM_KIND,
        namespace=FILESYSTEM_NAMESPACE,
        name=name,
        exception_type=FilesystemExtensionError,
    )


def creating_filesystem(
    suffix: str, *, filesystems: dict[str, Filesystem] | None = None
) -> str | None:
    """The filesystem that creates *suffix* images by default, or ``None``.

    ``disc create`` infers the filesystem from the target's extension via
    each filesystem's ``creates`` set. Returns ``None`` when no installed
    filesystem is the default creator for the extension (so the user must
    pass ``--filesystem``).
    """
    suffix = suffix.lower()
    active = _registered_filesystems() if filesystems is None else filesystems
    for name, filesystem in active.items():
        if suffix in filesystem.creates:
            return name
    return None


def _registered_filesystems() -> dict[str, Filesystem]:
    """Instantiate every registered filesystem, keyed by entry-point name."""
    manager = stevedore.ExtensionManager(
        namespace=FILESYSTEM_NAMESPACE,
        invoke_on_load=False,
        on_load_failure_callback=load_failure_callback,
    )
    return {ext.name: ext.plugin(name=ext.name) for ext in manager}


def identify(
    source: ImageSource,
    *,
    suffix_hint: str | None = None,
    filesystems: dict[str, Filesystem] | None = None,
) -> list[Identification]:
    """Identify the filesystem(s) on *source*, best candidate first.

    Returns the whole-image candidates ranked by confidence (extension
    only a tie-breaker), each with its reserved regions recursively
    identified in :attr:`Identification.contained`. An empty list means
    no installed filesystem recognised the image; :func:`survey` says why.

    *filesystems* overrides the discovered set — used by tests and to
    simulate a partial install (the extensibility invariant).
    """
    return survey(source, suffix_hint=suffix_hint, filesystems=filesystems).candidates


def survey(
    source: ImageSource,
    *,
    suffix_hint: str | None = None,
    filesystems: dict[str, Filesystem] | None = None,
) -> Survey:
    """Every installed filesystem's verdict on *source*.

    The :attr:`Survey.candidates` are what :func:`identify` returns; the
    :attr:`Survey.rejections` give each other filesystem's reason for
    declining the whole image, to explain an unrecognised one.
    """
    with reader_for(source, suffix_hint=suffix_hint) as reader:
        active = _registered_filesystems() if filesystems is None else filesystems
        candidates, rejections = _probe_region(reader, active, reader.suffix)
        whole = Partition(name="", start_sector=0, num_sectors=reader.size // BYTES_PER_SECTOR)
        return Survey(
            candidates=[
                replace(c, partition=replace(whole, name=c.filesystem)) for c in candidates
            ],
            rejections=rejections,
        )


def _probe_region(
    reader: ImageReader, filesystems: dict[str, Filesystem], suffix: str | None
) -> tuple[list[Identification], tuple[Rejection, ...]]:
    """Ranked candidates for the region in *reader*, recursion attached,
    and the rejections of the filesystems that declined it."""
    candidates: list[Identification] = []
    rejections: list[Rejection] = []
    for name, filesystem in filesystems.items():
        identification = filesystem.probe(reader)
        if identification is None:
            rejections.append(Rejection(name))
            continue
        if isinstance(identification, Rejection):
            rejections.append(identification)
            continue
        if identification.reserved_regions:
            identification = identification.with_contained(
                _recurse_regions(
                    identification.reserved_regions,
                    reader,
                    identification.geometry,
                    filesystems,
                )
            )
        candidates.append(identification)
    rejections.sort(key=lambda rejection: rejection.filesystem)
    return _rank(candidates, filesystems, suffix), tuple(rejections)


def _recurse_regions(
    regions: tuple[Partition, ...],
    reader: ImageReader,
    geometry: Geometry | None,
    filesystems: dict[str, Filesystem],
) -> tuple[Identification, ...]:
    """Identify each reserved region; name partitions by what's found there.

    Each region is read through the host's geometry (de-interleaved when
    the host is an interleaved floppy) so the tail filesystem sees a
    contiguous logical view.
    """
    contained: list[Identification] = []
    counts: dict[str, int] = {}
    for region in regions:
        sub_reader = region_reader(reader, geometry, region.start_sector, region.num_sectors)
        sub, _rejections = _probe_region(sub_reader, filesystems, None)
        if sub:
            name = sub[0].filesystem
            index = counts.get(name, 0)
            counts[name] = index + 1
            contained.append(replace(sub[0], partition=replace(region, name=name, index=index)))
        else:
            index = counts.get("", 0)
            counts[""] = index + 1
            contained.append(
                Identification(
                    filesystem="",
                    confidence=Confidence.POSSIBLE,
                    evidence=("reserved region; no installed filesystem recognised it",),
                    partition=replace(region, name="", index=index),
                )
            )
    return tuple(contained)


def _rank(
    candidates: list[Identification],
    filesystems: dict[str, Filesystem],
    suffix: str | None,
) -> list[Identification]:
    """Order *candidates* best-first: confidence, then extension, then priority."""

    def extension_agrees(identification: Identification) -> bool:
        filesystem = filesystems.get(identification.filesystem)
        return bool(suffix and filesystem and suffix in filesystem.extensions)

    def priority(identification: Identification) -> int:
        filesystem = filesystems.get(identification.filesystem)
        return filesystem.priority if filesystem is not None else 0

    ordered = sorted(candidates, key=lambda i: i.filesystem)
    ordered.sort(
        key=lambda i: (int(i.confidence), extension_agrees(i), priority(i)),
        reverse=True,
    )
    return ordered

"""Host directory tree → AFS image import.

Phase 18 of the oaknut-afs build. Walks a host-side directory
(optionally resolving per-file metadata via
:mod:`oaknut.file.host_bridge`) and drops every file and sub-dir
into the target AFS region through the public write path.

Mostly used by the ``scripts/build_library_images.py`` helper that
assembles the shipped ``.img`` assets from
``/Users/rjs/Code/beebium/discs/l3fs/libraries/econet-fs.tar``, but
also usable directly for ad-hoc bulk imports.

Names are filtered to AFS's 10-char character set: any character
forbidden by :class:`oaknut.afs.path.AFSPath` is replaced with
``_`` and the name is truncated to :data:`MAX_NAME_LENGTH`
characters. Files whose sanitised name would collide with an
existing entry in the same directory raise
:class:`AFSHostImportError` unless ``on_collision="skip"``.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from oaknut.afs.access import AFSAccess
from oaknut.afs.directory import MAX_NAME_LENGTH
from oaknut.afs.exceptions import AFSHostImportError
from oaknut.afs.types import AfsDate
from oaknut.file import AcornMeta
from oaknut.file.host_bridge import import_with_metadata

if TYPE_CHECKING:
    from oaknut.afs.afs import AFS
    from oaknut.afs.path import AFSPath


CollisionPolicy = Literal["error", "skip", "overwrite"]


def _sanitise_name(host_name: str) -> str:
    """Convert a host filename to a valid AFS name."""
    forbidden = set(". :/")
    cleaned = "".join("_" if ch in forbidden else ch for ch in host_name)
    # Strip trailing / leading whitespace or non-printable.
    cleaned = "".join(ch for ch in cleaned if 0x21 <= ord(ch) <= 0x7E)
    if not cleaned:
        cleaned = "UNNAMED"
    return cleaned[:MAX_NAME_LENGTH]


def _meta_to_access(meta: AcornMeta) -> AFSAccess:
    """Convert an :class:`AcornMeta` to an AFS access byte.

    ``AcornMeta.attr`` is the raw DFS/ADFS attribute byte as read
    from the host sidecar or xattr. Falls back to ``WR/`` (owner
    R+W) when no attribute info is present.
    """
    if meta.attr is None:
        return AFSAccess.from_string("WR/")
    # oaknut.file.Access is the DFS/ADFS Access IntFlag.
    from oaknut.file import Access as FileAccess

    attr = FileAccess(meta.attr)
    result = AFSAccess(0)
    if attr & FileAccess.L:
        result |= AFSAccess.LOCKED
    if attr & FileAccess.R:
        result |= AFSAccess.OWNER_READ
    if attr & FileAccess.W:
        result |= AFSAccess.OWNER_WRITE
    if attr & FileAccess.PR:
        result |= AFSAccess.PUBLIC_READ
    if attr & FileAccess.PW:
        result |= AFSAccess.PUBLIC_WRITE
    return result


def import_host_tree(
    target: "AFS",
    *,
    source: Path,
    target_path: "AFSPath | None" = None,
    on_collision: CollisionPolicy = "error",
) -> None:
    """Pull the host directory at ``source`` into ``target_path``.

    - ``source`` must be an existing directory on the host.
    - ``target_path`` defaults to the AFS root; must be a directory
      (created via ``mkdir`` if it doesn't yet exist).
    - Per-file metadata is resolved through
      :func:`oaknut.file.host_bridge.import_with_metadata` so INF
      sidecars and xattr-based schemes populate load/exec/access
      automatically.
    - Names longer than 10 chars or containing forbidden chars
      (``.``, ``:``, space) are sanitised.
    """
    if target_path is None:
        target_path = target.root
    if not source.is_dir():
        raise AFSHostImportError(f"source {source} is not a directory")
    if target_path.afs is not target:
        raise AFSHostImportError(
            "target_path must be bound to the target AFS handle"
        )

    # Ensure the landing directory exists.
    if not target_path.is_root() and not target_path.exists():
        target_path.mkdir()

    for entry in sorted(source.iterdir()):
        name = _sanitise_name(entry.name)
        child_path = target_path / name
        if child_path.exists():
            if on_collision == "error":
                raise AFSHostImportError(
                    f"target {child_path} already exists for host {entry}"
                )
            if on_collision == "skip":
                continue
            if on_collision == "overwrite":
                child_path.unlink()

        if entry.is_dir():
            child_path.mkdir()
            import_host_tree(
                target,
                source=entry,
                target_path=child_path,
                on_collision=on_collision,
            )
            continue

        # File: resolve metadata + content.
        clean_path, _label, meta = import_with_metadata(entry)
        data = clean_path.read_bytes()
        load = meta.load_addr if meta.load_addr is not None else 0
        exec_ = meta.exec_addr if meta.exec_addr is not None else 0
        access = _meta_to_access(meta)
        child_path.write_bytes(
            data,
            load_address=load,
            exec_address=exec_,
            access=access,
            date=AfsDate(datetime.date.today()),
        )

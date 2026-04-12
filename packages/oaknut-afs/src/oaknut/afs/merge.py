"""AFS → AFS subtree copy.

Walks the source directory tree recursively and recreates each
directory and file in the target through the public write path
(``write_bytes`` / ``mkdir``). Metadata — access byte, load
address, exec address, date — is preserved.

Used by :func:`oaknut.afs.wfsinit.initialise` to drop the shipped
library images into a freshly-initialised disc, and usable
directly for any AFS-to-AFS bulk copy.

The merge is a dry-walk + write pass when ``conflict="error"``:
we first walk the source collecting every target path that would
be written to, and if any already exists in the target we raise
before touching bytes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from oaknut.afs.exceptions import AFSMergeConflictError
from oaknut.afs.passwords import PASSWORDS_FILENAME

if TYPE_CHECKING:
    from oaknut.afs.afs import AFS
    from oaknut.afs.path import AFSPath


ConflictPolicy = Literal["error", "skip", "overwrite"]

# Files that are never copied during a merge. The Passwords file
# is per-disc and must not be overwritten by a library image's own
# Passwords file.
_EXCLUDED_NAMES: frozenset[str] = frozenset({PASSWORDS_FILENAME})


def merge(
    target: "AFS",
    source: "AFS",
    *,
    source_path: "AFSPath | None" = None,
    target_path: "AFSPath | None" = None,
    conflict: ConflictPolicy = "error",
    exclude: frozenset[str] | None = None,
) -> None:
    """Copy a directory subtree from ``source`` to ``target``.

    ``source_path`` defaults to ``source.root``; ``target_path``
    defaults to ``target.root``. Both must be directories.

    ``exclude`` is a set of entry names to skip during the merge.
    By default, the ``Passwords`` file is always excluded so that a
    library merge never overwrites the target disc's user records.

    ``conflict`` controls what happens when a destination name
    already exists:

    - ``"error"`` (default): refuse the whole merge with
      :class:`AFSMergeConflictError` before writing anything.
    - ``"skip"``: leave the existing target entry alone.
    - ``"overwrite"``: replace the target entry (its old bytes
      are released back to the allocator).
    """
    if exclude is None:
        exclude = _EXCLUDED_NAMES
    if source_path is None:
        source_path = source.root
    if target_path is None:
        target_path = target.root

    if not source_path.is_dir():
        raise ValueError(f"{source_path} is not a directory on source")
    if target_path.afs is not target:
        raise ValueError("target_path must be bound to the target AFS handle")
    if source_path.afs is not source:
        raise ValueError("source_path must be bound to the source AFS handle")

    # Ensure the target subtree root exists.
    if not target_path.is_root() and not target_path.exists():
        target_path.mkdir()

    # Dry-walk to collect conflicts if we are in "error" mode.
    if conflict == "error":
        conflicts: list[str] = []
        for src_descendant, tgt_descendant in _walk_pairs(
            source, source_path, target, target_path, exclude,
        ):
            if tgt_descendant.exists():
                conflicts.append(str(tgt_descendant))
        if conflicts:
            raise AFSMergeConflictError(
                f"merge conflicts at: {', '.join(conflicts[:5])}"
                + (f" (+ {len(conflicts) - 5} more)" if len(conflicts) > 5 else "")
            )

    # Actual copy pass.
    for src_descendant, tgt_descendant in _walk_pairs(
        source, source_path, target, target_path, exclude,
    ):
        src_stat = src_descendant.stat()
        if tgt_descendant.exists():
            if conflict == "skip":
                continue
            if conflict == "overwrite":
                tgt_descendant.unlink()
            # "error" mode was caught above.

        if src_stat.is_directory:
            tgt_descendant.mkdir(access=src_stat.access)
        else:
            data = src_descendant.read_bytes()
            tgt_descendant.write_bytes(
                data,
                load_address=src_stat.load_address,
                exec_address=src_stat.exec_address,
                access=src_stat.access,
                date=src_stat.date,
            )


def _walk_pairs(
    source: "AFS",
    source_root: "AFSPath",
    target: "AFS",
    target_root: "AFSPath",
    exclude: frozenset[str],
):
    """Yield ``(src_path, tgt_path)`` for every entry under ``source_root``.

    Entries whose leaf name is in *exclude* are silently skipped.
    The walk is pre-order: a directory is yielded before its
    contents, so ``mkdir`` happens before any file inside it is
    written.
    """
    stack = [source_root]
    while stack:
        src_dir = stack.pop()
        for src_entry in src_dir.iterdir():
            if src_entry.name in exclude:
                continue
            rel_parts = src_entry.parts[len(source_root.parts) :]
            tgt_entry = target_root
            for part in rel_parts:
                tgt_entry = tgt_entry / part
            yield src_entry, tgt_entry
            if src_entry.is_dir():
                stack.append(src_entry)

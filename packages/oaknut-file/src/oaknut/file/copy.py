"""Cross-filesystem file copy via duck-typed path objects.

All oaknut path types (DFSPath, ADFSPath, AFSPath) share a common
interface: ``read_bytes()``, ``write_bytes(data, load_address=,
exec_address=, ...)``, ``stat()``, ``exists()``, ``is_dir()``.
The :func:`copy_file` function copies a file between any two path
objects using only this interface, so it works across DFS, ADFS,
and AFS in any combination.

The destination's filesystem family is read directly from its
``_target_fs_kind`` class attribute — callers do not have to pass it
in. Access attributes are mapped via :mod:`oaknut.file.access_mapping`
so each filesystem receives access information in its native form
with sensible defaults for bits it cannot represent.
"""

from __future__ import annotations

from typing import Any

from oaknut.file.access_mapping import access_from_stat, access_to_write_kwargs


def copy_file(src: Any, dst: Any, **write_kwargs: Any) -> None:
    """Copy a single file from *src* to *dst*.

    Reads data and metadata (load address, exec address, access
    attributes) from *src* and writes them to *dst*. Both arguments
    must be path-like objects supporting ``read_bytes()``, ``stat()``,
    ``exists()``, ``is_dir()``, and ``write_bytes(data, ...)``.

    The destination's filesystem family is determined by its
    ``_target_fs_kind`` class attribute (``"dfs"``, ``"adfs"``, or
    ``"afs"``); access attributes are then mapped to the correct
    ``write_bytes`` keyword arguments via
    :func:`oaknut.file.access_mapping.access_to_write_kwargs`.
    Destinations without ``_target_fs_kind`` skip the access mapping
    and only ``load_address`` and ``exec_address`` are passed through —
    useful for duck-typed test doubles.

    Additional keyword arguments override source metadata.

    Raises:
        FileNotFoundError: If *src* does not exist.
        ValueError: If *src* is a directory.
    """
    if not src.exists():
        raise FileNotFoundError(f"source path does not exist: {src.name}")
    if src.is_dir():
        raise ValueError(f"cannot copy a directory: {src.name}")

    data = src.read_bytes()
    st = src.stat()

    kwargs: dict[str, Any] = {
        "load_address": getattr(st, "load_address", 0),
        "exec_address": getattr(st, "exec_address", 0),
    }

    target_fs = getattr(dst, "_target_fs_kind", None)
    if target_fs is not None:
        access = access_from_stat(st)
        kwargs.update(access_to_write_kwargs(access, target_fs))

    kwargs.update(write_kwargs)
    dst.write_bytes(data, **kwargs)

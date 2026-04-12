"""Cross-filesystem file copy via duck-typed path objects.

All oaknut path types (DFSPath, ADFSPath, AFSPath) share a common
interface: ``read_bytes()``, ``write_bytes(data, load_address=,
exec_address=, ...)``, ``stat()``, ``exists()``, ``is_dir()``.
The :func:`copy_file` function copies a file between any two path
objects using only this interface, so it works across DFS, ADFS,
and AFS in any combination.

Access attributes are mapped via :mod:`oaknut.file.access_mapping`
so that each filesystem receives access information in its native
form with sensible defaults for bits it cannot represent.
"""

from __future__ import annotations

from typing import Any

from oaknut.file.access_mapping import access_from_stat, access_to_write_kwargs


def copy_file(
    src: Any,
    dst: Any,
    *,
    target_fs: str | None = None,
    **write_kwargs: Any,
) -> None:
    """Copy a single file from *src* to *dst*.

    Reads data and metadata (load address, exec address, access
    attributes) from *src* and writes them to *dst*. Both arguments
    must be path-like objects supporting ``read_bytes()``, ``stat()``,
    ``exists()``, ``is_dir()``, and ``write_bytes(data, ...)``.

    *target_fs* identifies the destination filesystem (``"dfs"``,
    ``"adfs"``, or ``"afs"``) so access attributes can be mapped to
    the correct ``write_bytes`` keyword arguments. When ``None``, the
    access mapping is omitted — only ``load_address`` and
    ``exec_address`` are passed through.

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

    if target_fs is not None:
        access = access_from_stat(st)
        kwargs.update(access_to_write_kwargs(access, target_fs))

    kwargs.update(write_kwargs)
    dst.write_bytes(data, **kwargs)

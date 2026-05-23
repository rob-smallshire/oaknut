"""Cross-filesystem file copy via duck-typed path objects.

All oaknut path types (DFSPath, ADFSPath, AFSPath) share a common
``write_bytes`` signature that accepts a canonical
:class:`oaknut.file.Access` flag on its ``access`` keyword (#25),
so :func:`copy_file` no longer has to dispatch on the destination's
filesystem family — it just hands every destination the same
``access=`` value and lets the path's own ``write_bytes`` translate
to whatever the on-disc layout needs.
"""

from __future__ import annotations

from typing import Any

from oaknut.file.access_mapping import access_from_stat


def copy_file(src: Any, dst: Any, **write_kwargs: Any) -> None:
    """Copy a single file from *src* to *dst*.

    Reads data and metadata (load address, exec address, access
    attributes) from *src* and writes them to *dst*. Both arguments
    must be path-like objects supporting ``read_bytes()``, ``stat()``,
    ``exists()``, ``is_dir()``, and ``write_bytes(data, ...)``.

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
        "access": access_from_stat(st),
    }
    kwargs.update(write_kwargs)
    dst.write_bytes(data, **kwargs)

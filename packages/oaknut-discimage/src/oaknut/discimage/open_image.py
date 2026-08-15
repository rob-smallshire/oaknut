"""Open a disc-image file with the best available access.

Acorn filesystem code never needs the caller to specify a Python
``open()`` mode string. The host filesystem already gates writability
via permissions: if the user has write access to the image, the
filesystem layer opens it writable and mutations land on disc; if
the image is read-only on disc, the open transparently falls back
to a read-only mmap and any attempted mutation raises later from
the mmap layer.

This helper centralises the policy so DFS, ADFS, and AFS (through
ADFS) all behave identically.
"""

from __future__ import annotations

import mmap
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def open_image_mmap(filepath: Path, *, writable: bool = True) -> Iterator[tuple[mmap.mmap, bool]]:
    """Open ``filepath`` as an mmap, writable when the host allows it.

    With ``writable`` (the default) tries ``r+b`` first, falling back to
    ``rb`` on :class:`PermissionError`. Pass ``writable=False`` to force a
    read-only mmap — a caller that only reads (e.g. scanning committed test
    fixtures) uses this so no accidental write can ever be flushed back to the
    file; the read-only mapping makes any attempted mutation raise at once
    rather than silently persist. The yielded tuple is ``(mm, writable)`` so
    callers know whether to ``mm.flush()`` on clean exit.

    Args:
        filepath: Path to an existing disc-image file.
        writable: Open for writing when the host permits (default); ``False``
            forces a read-only mapping.

    Yields:
        ``(mmap, writable)`` — the mmap is sized to the whole file
        and held open for the duration of the ``with`` block.
    """
    if writable:
        try:
            f = open(filepath, "r+b")
            opened_writable = True
        except PermissionError:
            f = open(filepath, "rb")
            opened_writable = False
    else:
        f = open(filepath, "rb")
        opened_writable = False

    with f:
        access = mmap.ACCESS_WRITE if opened_writable else mmap.ACCESS_READ
        mm = mmap.mmap(f.fileno(), 0, access=access)
        try:
            yield mm, opened_writable
        finally:
            if opened_writable:
                mm.flush()

"""Extract a canonical access value from any filesystem's stat result.

The Acorn filesystem families expose file access differently:

- **DFS**: a single ``locked`` boolean, no ``.access``.
- **ADFS**: an :class:`Access` IntFlag directly.
- **AFS**: an :class:`Access` too — its stat translates its own on-disc
  ``AFSAccess`` byte to the canonical wire form (see
  :meth:`oaknut.afs.access.AFSAccess.to_acorn`), so this layer needs no
  knowledge of the AFS bit layout.

:func:`access_from_stat` reduces any of these to a canonical
:class:`Access`. It is used by :func:`oaknut.file.copy.copy_file` so a
cross-filesystem copy carries access as losslessly as the destination
allows.
"""

from __future__ import annotations

from typing import Any

from oaknut.file.access import Access

# Default access for a DFS file, which records only locked/unlocked: the
# owner can read and write, and there is no public-access concept.
_DFS_DEFAULT_ACCESS = Access.W | Access.R


def access_from_stat(st: Any) -> Access:
    """Extract a canonical :class:`Access` from any stat result.

    A stat with an :class:`Access` ``.access`` (ADFS, AFS) yields it
    directly; a DFS stat (only ``.locked``) yields ``WR/`` plus ``L`` when
    locked.
    """
    access_val = getattr(st, "access", None)
    if isinstance(access_val, Access):
        return access_val

    result = _DFS_DEFAULT_ACCESS
    if getattr(st, "locked", False):
        result |= Access.L
    return result

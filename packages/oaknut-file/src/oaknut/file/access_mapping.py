"""Cross-filesystem access attribute mapping.

The three Acorn filesystem families represent file access differently:

- **DFS**: a single ``locked`` boolean.
- **ADFS**: six individual boolean flags (owner R/W/E, locked, public
  R/W) exposed as an ``Access`` IntFlag.
- **AFS**: an ``AFSAccess`` byte with a different bit layout (public
  R/W in low bits, owner R/W above, locked at bit 4, directory at
  bit 5).

This module provides two functions:

- :func:`access_from_stat` extracts a canonical ``Access`` value from
  any stat result, regardless of which filesystem produced it.
- :func:`access_to_write_kwargs` converts an ``Access`` value into
  the keyword arguments expected by a target filesystem's
  ``write_bytes()`` method.

These are used by :func:`oaknut.file.copy.copy_file` to map access
attributes as losslessly as possible when copying between filesystems.
When a target filesystem cannot represent a source attribute (e.g.
DFS has no public-read bit), the information is silently dropped.
When the source has fewer bits than the target (e.g. DFS → ADFS),
sensible defaults are applied: an unlocked DFS file becomes ``WR/``
on ADFS.
"""

from __future__ import annotations

from typing import Any

from oaknut.file.access import Access

# Default access for a DFS file that has no access attributes beyond
# locked/unlocked. WR/ is what DFS files effectively have — the owner
# can read and write, and there is no concept of public access.
_DFS_DEFAULT_ACCESS = Access.W | Access.R


def access_from_stat(st: Any) -> Access:
    """Extract a canonical ``Access`` from any stat result.

    Recognises three stat shapes:

    - **Has** ``.access`` attribute that is an ``Access`` IntFlag
      (ADFSStat) — returns it directly.
    - **Has** ``.access`` attribute with AFS-style bit layout
      (AFSAccess or similar) — maps the bits to ``Access``.
    - **Has** ``.locked`` but no ``.access`` (DFSStat) — returns
      ``WR/`` with or without ``L``.
    """
    if hasattr(st, "access"):
        access_val = st.access
        if isinstance(access_val, Access):
            return access_val
        # AFS-style access: different bit layout. Map to Access.
        return _access_from_afs_bits(int(access_val))

    # DFS: only locked bit.
    locked = getattr(st, "locked", False)
    result = _DFS_DEFAULT_ACCESS
    if locked:
        result |= Access.L
    return result


def _access_from_afs_bits(afs_byte: int) -> Access:
    """Map AFS on-disc access bits to the canonical ``Access`` IntFlag.

    AFS layout:  bit 0 = public R, 1 = public W, 2 = owner R,
                 3 = owner W, 4 = locked, 5 = directory.

    Access layout: bit 0 = owner R, 1 = owner W, 2 = execute,
                   3 = locked, 4 = public R, 5 = public W.
    """
    result = Access(0)
    if afs_byte & 0x04:
        result |= Access.R
    if afs_byte & 0x08:
        result |= Access.W
    if afs_byte & 0x10:
        result |= Access.L
    if afs_byte & 0x01:
        result |= Access.PR
    if afs_byte & 0x02:
        result |= Access.PW
    return result


def _access_to_afs_bits(access: Access) -> int:
    """Map canonical ``Access`` to AFS on-disc access byte."""
    result = 0
    if access & Access.R:
        result |= 0x04
    if access & Access.W:
        result |= 0x08
    if access & Access.L:
        result |= 0x10
    if access & Access.PR:
        result |= 0x01
    if access & Access.PW:
        result |= 0x02
    return result


def access_to_write_kwargs(access: Access, target_fs: str) -> dict[str, Any]:
    """Convert ``Access`` to ``write_bytes`` keyword arguments.

    *target_fs* is one of ``"dfs"``, ``"adfs"``, or ``"afs"``
    (case-insensitive).

    Returns a dict suitable for ``**``-splatting into the target
    path's ``write_bytes()`` call.
    """
    fs = target_fs.lower()
    if fs == "dfs":
        return {"locked": bool(access & Access.L)}
    elif fs == "adfs":
        return {"locked": bool(access & Access.L)}
    elif fs == "afs":
        return {"access": _access_to_afs_bits(access)}
    else:
        raise ValueError(f"unknown target filesystem: {target_fs!r}")

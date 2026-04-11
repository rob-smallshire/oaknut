"""Extended attribute read/write for Acorn file metadata.

Two namespaces are supported:

- ``user.acorn.*`` (preferred): the oaknut-file convention
- ``user.econet_*``: PiEconetBridge legacy convention

Read functions for the Acorn namespace fall back to the Econet
namespace when the preferred attributes are absent. Write functions
use whichever namespace is named explicitly.

Platform support:

- **Linux**: uses ``os.setxattr`` / ``os.getxattr``
- **macOS**: uses the ``xattr`` package (install with ``pip install oaknut-file[xattr]``)
- **Other**: not supported
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

from oaknut.file.meta import AcornMeta


# --- Acorn namespace constants ---
_ACORN_LOAD = "user.acorn.load"
_ACORN_EXEC = "user.acorn.exec"
_ACORN_ATTR = "user.acorn.attr"

# --- Econet namespace constants ---
_ECONET_OWNER = "user.econet_owner"
_ECONET_LOAD = "user.econet_load"
_ECONET_EXEC = "user.econet_exec"
_ECONET_PERM = "user.econet_perm"


def _set_xattrs(filepath: Path, attrs: dict[str, str]) -> None:
    """Set extended attributes on a file.

    Uses ``os.setxattr`` on Linux, or the ``xattr`` package on macOS.
    """
    path_str = str(filepath)
    if hasattr(os, "setxattr"):
        for name, value in attrs.items():
            os.setxattr(path_str, name, value.encode("ascii"))
    else:
        import xattr

        x = xattr.xattr(path_str)
        for name, value in attrs.items():
            x.set(name, value.encode("ascii"))


def _get_xattr(filepath: Path, name: str) -> str | None:
    """Read a single extended attribute, or None if absent."""
    path_str = str(filepath)
    try:
        if hasattr(os, "getxattr"):
            value = os.getxattr(path_str, name)
        else:
            import xattr

            x = xattr.xattr(path_str)
            value = x.get(name)
        return value.decode("ascii")
    except (OSError, KeyError):
        return None


def write_acorn_xattrs(
    filepath: Union[str, Path],
    load_addr: int,
    exec_addr: int,
    attr: int | None = None,
) -> None:
    """Write Acorn file metadata as extended attributes.

    Writes ``user.acorn.load``, ``user.acorn.exec``, and optionally
    ``user.acorn.attr`` as uppercase hex strings.
    """
    attrs = {
        _ACORN_LOAD: f"{load_addr:08X}",
        _ACORN_EXEC: f"{exec_addr:08X}",
    }
    if attr is not None:
        attrs[_ACORN_ATTR] = f"{attr:02X}"
    _set_xattrs(Path(filepath), attrs)


def read_acorn_xattrs(filepath: Union[str, Path]) -> AcornMeta | None:
    """Read Acorn file metadata from extended attributes.

    Tries the ``user.acorn.*`` namespace first; falls back to
    ``user.econet_*`` if the preferred namespace is absent.
    Returns ``None`` if neither namespace is present.
    """
    filepath = Path(filepath)

    load = _get_xattr(filepath, _ACORN_LOAD)
    if load is not None:
        exec_val = _get_xattr(filepath, _ACORN_EXEC)
        attr_val = _get_xattr(filepath, _ACORN_ATTR)
        return AcornMeta(
            load_addr=int(load, 16),
            exec_addr=int(exec_val, 16) if exec_val is not None else None,
            attr=int(attr_val, 16) if attr_val is not None else None,
        )

    # Fall back to Econet namespace
    return read_econet_xattrs(filepath)


def write_econet_xattrs(
    filepath: Union[str, Path],
    load_addr: int,
    exec_addr: int,
    attr: int | None = None,
    owner: int = 0,
) -> None:
    """Write PiEconetBridge-compatible extended attributes.

    Writes the four ``user.econet_*`` attributes used by PiEconetBridge.
    When *attr* is None, the conventional default of ``0x17`` (LR/R)
    is written.
    """
    perm = attr if attr is not None else 0x17
    attrs = {
        _ECONET_OWNER: f"{owner:04X}",
        _ECONET_LOAD: f"{load_addr:08X}",
        _ECONET_EXEC: f"{exec_addr:08X}",
        _ECONET_PERM: f"{perm:02X}",
    }
    _set_xattrs(Path(filepath), attrs)


def read_econet_xattrs(filepath: Union[str, Path]) -> AcornMeta | None:
    """Read PiEconetBridge extended attributes.

    Returns ``None`` if no Econet attributes are present.
    """
    filepath = Path(filepath)

    load = _get_xattr(filepath, _ECONET_LOAD)
    if load is None:
        return None

    exec_val = _get_xattr(filepath, _ECONET_EXEC)
    perm_val = _get_xattr(filepath, _ECONET_PERM)

    return AcornMeta(
        load_addr=int(load, 16),
        exec_addr=int(exec_val, 16) if exec_val is not None else None,
        attr=int(perm_val, 16) if perm_val is not None else None,
    )

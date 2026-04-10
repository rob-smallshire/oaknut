"""INF sidecar file parsing and formatting.

Supports two INF flavours:

- **Traditional**: ``filename load exec length [attr]``
- **PiEconetBridge**: ``owner load exec perm``

Also handles the ``"L"`` and ``"Locked"`` markers written by
some ADFS and DFS exporters.
"""

from __future__ import annotations

from pathlib import Path

from oaknut_file.access import Access
from oaknut_file.formats import SOURCE_INF_PIEB, SOURCE_INF_TRAD
from oaknut_file.meta import AcornMeta


def _is_hex(s: str) -> bool:
    """Check if a string is a valid hexadecimal number."""
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def parse_inf_line(line: str) -> tuple[str, AcornMeta] | None:
    """Parse an INF sidecar line, auto-detecting the format.

    Returns ``(source_label, metadata)`` or ``None`` if the line
    cannot be parsed.

    The *source_label* is ``"inf-trad"`` or ``"inf-pieb"``.
    """
    line = line.strip()
    if not line:
        return None

    parts = line.split()
    if len(parts) < 4:
        return None

    first_is_hex = _is_hex(parts[0])

    try:
        if not first_is_hex:
            # First field is the filename — must be traditional INF
            return _parse_trad_inf(parts)

        # All fields could be hex. Distinguish by field[3] width:
        # Traditional INF length field is always 8-digit hex; PiEB perm
        # is short (1-2 digits).
        if len(parts[3]) == 8 and _is_hex(parts[3]):
            return _parse_trad_inf(parts)

        # PiEconetBridge: owner load exec perm
        load_addr = int(parts[1], 16)
        exec_addr = int(parts[2], 16)
        attr = int(parts[3], 16)
        meta = AcornMeta(load_addr=load_addr, exec_addr=exec_addr, attr=attr)
        meta.filetype = meta.infer_filetype()
        return SOURCE_INF_PIEB, meta
    except (ValueError, IndexError):
        return None


def _parse_trad_inf(parts: list[str]) -> tuple[str, AcornMeta] | None:
    """Parse a traditional INF line that has already been split."""
    load_addr = int(parts[1], 16)
    exec_addr = int(parts[2], 16)
    # parts[3] is length, informational only
    attr = None

    if len(parts) > 4:
        token = parts[4]
        if token == "L" or token == "Locked":
            attr = int(Access.R | Access.W | Access.L)
        else:
            attr = int(token, 16)

    meta = AcornMeta(load_addr=load_addr, exec_addr=exec_addr, attr=attr)
    meta.filetype = meta.infer_filetype()
    return SOURCE_INF_TRAD, meta


def format_trad_inf_line(
    filename: str,
    load_addr: int,
    exec_addr: int,
    length: int,
    attr: int | None = None,
) -> str:
    """Format a traditional INF line.

    Returns a string like ``"HELLO    00001900 00008023 00000100 03"``.
    """
    line = f"{filename:<11s} {load_addr:08X} {exec_addr:08X} {length:08X}"
    if attr is not None:
        line += f" {attr:02X}"
    return line


def format_pieb_inf_line(
    load_addr: int,
    exec_addr: int,
    attr: int | None = None,
    owner: int = 0,
) -> str:
    """Format a PiEconetBridge INF line.

    Returns a string like ``"0 ffffdd00 ffffdd00 17"``.
    """
    perm = attr if attr is not None else 0x17
    return f"{owner:x} {load_addr:x} {exec_addr:x} {perm:x}"


def read_inf_file(filepath: Path) -> tuple[str, AcornMeta] | None:
    """Read and parse an INF sidecar file.

    Returns ``(source_label, metadata)`` or ``None`` if the file
    does not exist or cannot be parsed.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return None
    text = filepath.read_text().strip()
    if not text:
        return None
    return parse_inf_line(text.split("\n")[0])


def write_inf_file(filepath: Path, content: str) -> None:
    """Write an INF sidecar file."""
    Path(filepath).write_text(content + "\n")

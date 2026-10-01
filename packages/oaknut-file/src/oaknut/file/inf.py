"""INF sidecar file parsing and formatting.

Supports two INF flavours:

- **Traditional**, read and written per the Stardot INF format
  specification (Tom Seddon,
  https://github.com/stardot/inf_format/blob/main/inf_format_full.md):
  ``name load exec length access …``, with its alternative short forms,
  quoted and percent-encoded names, the ``TAPE`` prefix, extra info
  fields and ``NEXT``. Where the specification leaves latitude or is
  silent, oaknut follows J.G. Harston (*Storing Acorn/BBC metadata on
  other systems*, https://mdfs.net/Docs/Comp/BBC/Filing/Metadata): a lock
  marker means ``&19``, an omitted access field ``&33``, and an omitted
  exec address is the load address.
- **PiEconetBridge**: ``owner load exec perm [homeof]``, whose perm byte
  has its own layout (see :mod:`oaknut.file.pieb`).
"""

from __future__ import annotations

from pathlib import Path

from oaknut.file.access import ACCESS_BYTE_MASK, Access, parse_access
from oaknut.file.formats import SOURCE_INF_PIEB, SOURCE_INF_TRAD
from oaknut.file.meta import AcornMeta
from oaknut.file.pieb import PIEB_ACCESS, PIEB_DEFAULT_PERM

#: The character encoding INF file text is read and written in. Latin-1
#: maps every byte to one character and back, so the line's bytes survive
#: intact; a name's bytes are then decoded with the medium's own name
#: codec (the *encoding* arguments below), which defaults to this.
INF_ENCODING = "latin-1"

_SPACES = " \t"
_DQUOTE = '"'

#: Access for a traditional INF with no access field (J.G. Harston).
_DEFAULT_ACCESS = 0x33
#: Access for a lock marker — Locked, LOCKED, or a bare L — "Locked on DFS"
#: (J.G. Harston; the Stardot specification permits implying other bits).
_LOCKED_ACCESS = 0x19
_LOCK_MARKERS = frozenset({"Locked", "LOCKED", "L"})

#: The Stardot specification's case-sensitive access letters.
_SYMBOLIC_BITS = {
    "R": 0x01,
    "W": 0x02,
    "E": 0x04,
    "L": 0x08,
    "r": 0x10,
    "w": 0x20,
    "e": 0x40,
    "l": 0x80,
    "D": 0x00,  # a directory marker, with no access bit
    "d": 0x00,
}


def _is_hex(s: str) -> bool:
    """Check if a string is a valid hexadecimal number."""
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def _first_line(text: str) -> str:
    """*text* up to its first CR or LF (later lines are reserved)."""
    for index, ch in enumerate(text):
        if ch in "\r\n":
            return text[:index]
    return text


def parse_inf_line(line: str, *, encoding: str = INF_ENCODING) -> tuple[str, AcornMeta] | None:
    """Parse an INF sidecar line, auto-detecting the format.

    Returns ``(source_label, metadata)`` or ``None`` if the line
    cannot be parsed. Only the first line of *line* is read. *line* is
    INF text in :data:`INF_ENCODING`, one character per byte. *encoding*
    is the name codec of the medium the file belongs to: a name's bytes,
    raw or percent-encoded, are decoded with it. Bytes it cannot decode
    are kept as their Latin-1 characters, for the destination's own name
    rules to judge.

    The *source_label* is ``"inf-trad"`` or ``"inf-pieb"``.
    """
    line = _first_line(line)
    parts = line.split()
    if len(parts) < 2:
        return None
    if _is_pieb(parts):
        return _parse_pieb_inf(parts)
    return _parse_trad_inf(line, encoding)


def _is_pieb(parts: list[str]) -> bool:
    """Whether split fields look like a PiEconetBridge line.

    PiEB writes ``owner load exec perm [homeof]``, every field hex, with a
    one- or two-digit perm. A traditional line with a hex-looking name
    has an 8-digit length (or no length at all) in that position.
    """
    return len(parts) in (4, 5) and all(_is_hex(part) for part in parts) and len(parts[3]) <= 2


def _parse_pieb_inf(parts: list[str]) -> tuple[str, AcornMeta]:
    load_address = int(parts[1], 16)
    exec_address = int(parts[2], 16)
    # PiEB's perm byte has its own layout (lock and execute swapped).
    attr = int(PIEB_ACCESS.to_canonical(int(parts[3], 16)))
    meta = AcornMeta(load_address=load_address, exec_address=exec_address, access=attr)
    meta.filetype = meta.infer_filetype()
    return SOURCE_INF_PIEB, meta


class _Scanner:
    """Walks one traditional INF line field by field."""

    def __init__(self, line: str, encoding: str):
        self.line = line
        self.encoding = encoding
        self.index = 0

    def skip_spaces(self) -> None:
        while self.index < len(self.line) and self.line[self.index] in _SPACES:
            self.index += 1

    def at_end(self) -> bool:
        self.skip_spaces()
        return self.index >= len(self.line)

    def field(self) -> str:
        """The next run of non-space characters."""
        begin = self.index
        while self.index < len(self.line) and self.line[self.index] not in _SPACES:
            self.index += 1
        return self.line[begin : self.index]

    def string_field(self) -> tuple[str, bool] | None:
        """The next string field and whether it was quoted; ``None`` if malformed."""
        if self.line[self.index] != _DQUOTE:
            raw = self.field().encode(INF_ENCODING, errors="replace")
            return _decode_name(raw, self.encoding), False
        end = self.line.find(_DQUOTE, self.index + 1)
        if end < 0:
            return None  # an unterminated quoted string
        quoted = self.line[self.index + 1 : end]
        self.index = end + 1
        raw = _percent_decode(quoted)
        return None if raw is None else (_decode_name(raw, self.encoding), True)


def _percent_decode(quoted: str) -> bytes | None:
    """The bytes RFC 3986 percent-encoded *quoted* stands for; ``None`` if malformed."""
    out = bytearray()
    index = 0
    while index < len(quoted):
        ch = quoted[index]
        if ch == "%":
            digits = quoted[index + 1 : index + 3]
            if len(digits) != 2 or not _is_hex(digits):
                return None
            out.append(int(digits, 16))
            index += 3
        else:
            out += ch.encode(INF_ENCODING, errors="replace")
            index += 1
    return bytes(out)


def _decode_name(raw: bytes, encoding: str) -> str:
    """Name bytes in the medium's *encoding*, else as Latin-1 characters."""
    try:
        return raw.decode(encoding)
    except UnicodeDecodeError:
        return raw.decode(INF_ENCODING)


def _address(field: str) -> int:
    """A load or exec address, sign-extending the 6-digit DFS style ``FFxxxx``."""
    value = int(field, 16)
    if len(field) == 6 and (value & 0xFF0000) == 0xFF0000:
        value |= 0xFFFF0000
    return value


def _symbolic_access(field: str) -> int | None:
    """An access field that can only be access, or ``None`` if it may be hex."""
    if field in _LOCK_MARKERS:
        return _LOCKED_ACCESS
    if field in ("E", "e", "D", "d"):
        return _SYMBOLIC_BITS[field]
    if "/" in field:
        # oaknut's owner/public form, case-insensitive as in the CLI.
        try:
            return int(parse_access(field))
        except ValueError:
            return None
    if _is_hex(field):
        return None
    if field and all(ch in _SYMBOLIC_BITS for ch in field):
        value = 0
        for ch in field:
            value |= _SYMBOLIC_BITS[ch]
        return value
    return None


def _parse_trad_inf(line: str, encoding: str = INF_ENCODING) -> tuple[str, AcornMeta] | None:
    """Parse a traditional INF line (Stardot INF syntaxes 1, 2 and 3)."""
    scanner = _Scanner(line, encoding)
    if scanner.at_end():
        return None
    name_field = scanner.string_field()
    if name_field is None:
        return None
    name, quoted = name_field
    if not quoted and name == "TAPE" and not scanner.at_end():
        # The deprecated TAPE prefix: the next field is the name.
        name_field = scanner.string_field()
        if name_field is None:
            return None
        name, quoted = name_field

    load_address = exec_address = access = None
    unreadable_access = False
    position = 0
    try:
        while not scanner.at_end():
            field = scanner.field()
            if "=" in field or field == "NEXT":
                break  # extra info fields, or NEXT: nothing further is metadata
            if position == 0:
                # Load address (syntaxes 1 and 2), or access alone (syntax 3).
                symbolic = _symbolic_access(field)
                if symbolic is not None:
                    access = symbolic
                    break
                load_address = _address(field)
            elif position == 1:
                exec_address = _address(field)
            elif position == 2:
                # Length (syntax 1), or a DFS lock marker (syntax 2).
                if field in _LOCK_MARKERS:
                    access = _LOCKED_ACCESS
                    break
                int(field, 16)
            elif position == 3:
                symbolic = _symbolic_access(field)
                if symbolic is not None:
                    access = symbolic
                else:
                    try:
                        access = int(field, 16)
                    except ValueError:
                        # An unreadable access field keeps the addresses but
                        # leaves the access unknown, rather than the default.
                        unreadable_access = True
                        break
            # Later hex fields (dates, accounts) are not modelled.
            position += 1
    except ValueError:
        if load_address is None:
            return None

    if load_address is None and access is None:
        return None
    if load_address is not None:
        if exec_address is None:
            exec_address = load_address
        if access is None and not unreadable_access:
            access = _DEFAULT_ACCESS

    meta = AcornMeta(load_address=load_address, exec_address=exec_address, access=access, name=name)
    if load_address is not None:
        meta.filetype = meta.infer_filetype()
    return SOURCE_INF_TRAD, meta


def _format_name(name: str, encoding: str) -> str:
    """*name* as an INF string field, quoted and percent-encoded if it needs it.

    The field holds the name's bytes in the medium's *encoding*, so the
    quoting rules apply to those bytes, not to the characters.
    """
    try:
        raw = name.encode(encoding)
    except UnicodeEncodeError:
        raw = name.encode(INF_ENCODING, errors="replace")
    needs_quoting = (
        raw == b""
        or raw == b"TAPE"
        or raw.startswith(b'"')
        or any(not 0x21 <= byte <= 0x7E for byte in raw)
    )
    if not needs_quoting:
        return raw.decode("ascii")
    encoded = []
    for byte in raw:
        if 0x20 <= byte <= 0x7E and byte not in (0x22, 0x25):
            encoded.append(chr(byte))
        else:
            encoded.append(f"%{byte:02X}")
    return _DQUOTE + "".join(encoded) + _DQUOTE


def format_trad_inf_line(
    filename: str,
    load_address: int,
    exec_address: int,
    length: int,
    attr: int | None = None,
    *,
    encoding: str = INF_ENCODING,
) -> str:
    """Format a traditional INF line, per the Stardot producer rules.

    Addresses and length are 8-digit hex and the access byte 2-digit hex;
    attribute bits above the access byte (bits 8–10) are not written.
    A name that is empty, literally ``TAPE``, starts with a double quote,
    or holds a space or any character outside printable 7-bit ASCII is
    quoted, with ``"``, ``%`` and such characters percent-encoded.
    *encoding* is the name codec of the medium the file comes from: the
    name is written as its bytes in that codec, and the rules above are
    applied to those bytes, as the Stardot specification requires.
    Returns a string like
    ``"HELLO    00001900 00008023 00000100 03"``.
    """
    line = (
        f"{_format_name(filename, encoding):<11s} "
        f"{load_address:08X} {exec_address:08X} {length:08X}"
    )
    if attr is not None:
        line += f" {attr & ACCESS_BYTE_MASK:02X}"
    return line


def format_pieb_inf_line(
    load_address: int,
    exec_address: int,
    attr: int | None = None,
    owner: int = 0,
) -> str:
    """Format a PiEconetBridge INF line.

    *attr* is canonical access, written in PiEB's own ``perm`` layout;
    ``None`` gives PiEB's default for a new file, ``WR/R``. Returns a
    string like ``"0 ffffdd00 ffffdd00 13"``.
    """
    perm = PIEB_DEFAULT_PERM if attr is None else PIEB_ACCESS.from_canonical(Access(attr))
    return f"{owner:x} {load_address:x} {exec_address:x} {perm:x}"


def read_inf_file(filepath: Path, *, encoding: str = INF_ENCODING) -> tuple[str, AcornMeta] | None:
    """Read and parse an INF sidecar file.

    Returns ``(source_label, metadata)`` or ``None`` if the file
    does not exist or cannot be parsed. *encoding* is the name codec of
    the medium the file is bound for, as for :func:`parse_inf_line`.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return None
    # Read the bytes, not host-decoded text, so 8-bit names from older tools
    # survive whatever the host's default encoding.
    text = filepath.read_bytes().decode(INF_ENCODING).lstrip()
    if not text:
        return None
    return parse_inf_line(text, encoding=encoding)


def write_inf_file(filepath: Path, content: str) -> None:
    """Write an INF sidecar file."""
    Path(filepath).write_bytes((content + "\n").encode(INF_ENCODING))

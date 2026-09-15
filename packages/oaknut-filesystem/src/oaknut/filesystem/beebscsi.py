"""BeebSCSI / Pi1MHz ``.cfg`` extended-attributes sidecars.

A BeebSCSI hard-drive LUN on an SD card carries a ``scsiN.cfg`` text file
alongside its raw ``scsiN.dat`` image. The ``.cfg`` holds SCSI mode-page
geometry plus drive identity — richer than the 22-byte binary ``.dsc``,
and preferred by the firmware. Crucially it records sectors-per-track
(``ModePage3``), which the ``.dsc`` cannot carry, so a ``.cfg`` describes
non-default geometries (an IDE 4x64 layout, say) that a ``.dsc`` would
silently report as the Acorn default of 33.

The format is a line-oriented ``Key=Value`` text file (see the Pi1MHz
firmware ``fileparser.c`` / ``filesystem.c``): ``#`` starts a comment
(whole-line or trailing); keys are case-insensitive and start a line;
most values are hex byte strings (``NUMSTRING``), a few are literal text
(``STRING``) or a decimal integer (``INTEGER``). Unknown keys are ignored.

:class:`BeebScsiConfig` parses a ``.cfg`` while preserving its comments,
layout, and unknown lines, so a file can be read, its geometry adjusted,
and written back near-verbatim — mirroring the firmware's own in-place
rewrite. :meth:`BeebScsiConfig.default` seeds a fresh config to write
alongside a newly created image.

Geometry is resolved exactly as ``filesystemConfigToLunGeometry`` does:
  * block size  -- ``LBADescriptor`` bytes 5-7 (big-endian), default 256
  * sectors/track -- ``ModePage3`` bytes 10-11 (big-endian), default 33
  * cylinders/heads -- ``ModePage0`` bytes 1-2 / byte 3, else ``ModePage4``
    bytes 3-4 / byte 5
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from oaknut.discimage import BYTES_PER_SECTOR
from oaknut.filesystem.exceptions import BeebScsiConfigError
from oaknut.filesystem.geometry import Geometry, winchester_geometry

_DEFAULT_BLOCK_SIZE = BYTES_PER_SECTOR  # 256
_DEFAULT_SECTORS_PER_TRACK = 33

# Value kinds, matching the firmware's parserkey types.
_HEX = "hex"  # NUMSTRING -- hex byte string
_STR = "str"  # STRING    -- literal text to end of line / '#'
_INT = "int"  # INTEGER   -- decimal (strtol base 0)

#: Recognised keys and their value kind (from ``scsiattributes`` in the
#: Pi1MHz firmware ``filesystem.c``). Canonical spelling; matching is
#: case-insensitive.
_KEY_KINDS: dict[str, str] = {
    "Title": _STR,
    "Description": _STR,
    "Inquiry": _HEX,
    "ModeParamHeader": _HEX,
    "LBADescriptor": _HEX,
    "ModePage0": _HEX,
    "ModePage1": _HEX,
    "ModePage3": _HEX,
    "WritPage3": _HEX,
    "ModePage4": _HEX,
    "ModePage32": _HEX,
    "ModePage33": _HEX,
    "ModePage35": _HEX,
    "ModePage36": _HEX,
    "ModePage37": _HEX,
    "ModePage38": _HEX,
    "LDUserCode": _STR,
    "LDVideoXoffset": _INT,
}
_CANONICAL = {name.lower(): name for name in _KEY_KINDS}

_KEY_TOKEN = re.compile(r"[A-Za-z0-9]+")
_SEP = re.compile(r"[ \t=]*")
_HEX_VALUE = re.compile(r"[^\s#]*")

#: A 23-byte ``ModePage3`` (Format Device Parameters) used as the basis
#: when synthesising geometry: sectors/track at 10-11, bytes/sector at
#: 12-13, interleave 0x0008. Overwritten field-by-field by
#: :meth:`BeebScsiConfig.set_geometry`.
_MODEPAGE3_BASE = bytes(
    [0x03, 0x15, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x21, 0x01, 0x00, 0, 0x08, 0, 0, 0, 0, 0, 0, 0]
)


@dataclass
class _KeyEntry:
    """One recognised ``Key=Value`` line, kept so it can be rewritten.

    *indent*/*key_text*/*sep*/*suffix* preserve the exact surrounding text
    (leading whitespace, the key as written, the ``=``/whitespace run, and
    any trailing comment) so :meth:`BeebScsiConfig.render` reproduces the
    line when the value is unchanged.
    """

    canonical: str
    kind: str
    value: object
    indent: str = ""
    key_text: str = ""
    sep: str = "="
    suffix: str = ""

    def render(self) -> str:
        key = self.key_text or self.canonical
        return f"{self.indent}{key}{self.sep}{_format(self.kind, self.value)}{self.suffix}"


def _format(kind: str, value: object) -> str:
    if kind == _HEX:
        assert isinstance(value, (bytes, bytearray))
        return value.hex().upper()
    if kind == _INT:
        return str(value)
    return str(value)


def _decode_hex(token: str) -> bytes | None:
    """Decode a ``NUMSTRING`` hex token, or ``None`` if malformed.

    Tolerates an optional ``0x`` prefix. An odd digit count or a non-hex
    character makes the value unusable; the caller keeps the line verbatim
    rather than register a bad key (as the firmware skips it).
    """
    if token[:2].lower() == "0x":
        token = token[2:]
    if not token or len(token) % 2 or not all(c in "0123456789abcdefABCDEF" for c in token):
        return None
    return bytes.fromhex(token)


class BeebScsiConfig:
    """A parsed BeebSCSI ``.cfg`` that round-trips near-verbatim.

    Build one with :meth:`parse` (from an existing file's text) or
    :meth:`default` (a fresh template to populate). Read geometry via
    :attr:`geometry` and the CHS properties; change it with
    :meth:`set_geometry`; serialise with :meth:`render`.
    """

    def __init__(self) -> None:
        # Verbatim lines (comments/blank/unknown) as str; recognised keys
        # as _KeyEntry — in source order.
        self._lines: list[str | _KeyEntry] = []
        self._index: dict[str, _KeyEntry] = {}

    # -- construction -------------------------------------------------------

    @classmethod
    def parse(cls, text: str) -> BeebScsiConfig:
        """Parse ``.cfg`` *text*, preserving comments and unknown lines."""
        cfg = cls()
        for line in text.split("\n"):
            cfg._lines.append(cfg._parse_line(line))
        return cfg

    @classmethod
    def default(cls) -> BeebScsiConfig:
        """A fresh config with sensible identity pages and no real geometry.

        The caller sets the geometry with :meth:`set_geometry` before
        rendering. Geometry defaults to a 1x1x33 placeholder so a config
        rendered without a :meth:`set_geometry` call is still well-formed.
        """
        cfg = cls()
        cfg._lines.append("# BeebSCSI / Pi1MHz LUN extended attributes, written by oaknut.")
        cfg._lines.append("# Values are SCSI mode pages in hex; geometry is in ModePage0/3/4.")
        cfg._lines.append("")
        cfg.set_title("oaknut")
        cfg.set_description("oaknut-generated ADFS hard disc")
        cfg._set(_KeyEntry("ModeParamHeader", _HEX, bytes([0, 0, 0, 0x08])))
        cfg.set_geometry(cylinders=1, heads=1, sectors_per_track=_DEFAULT_SECTORS_PER_TRACK)
        return cfg

    def _parse_line(self, line: str) -> str | _KeyEntry:
        stripped = line.lstrip(" \t")
        indent = line[: len(line) - len(stripped)]
        if not stripped or stripped.startswith("#"):
            return line
        match = _KEY_TOKEN.match(stripped)
        if match is None:
            return line
        canonical = _CANONICAL.get(match.group(0).lower())
        if canonical is None:
            return line  # unknown key -- keep verbatim

        key_text = match.group(0)
        rest = stripped[match.end() :]
        sep = _SEP.match(rest).group(0)
        after = rest[len(sep) :]
        kind = _KEY_KINDS[canonical]

        if kind == _HEX:
            token = _HEX_VALUE.match(after).group(0)
            suffix = after[len(token) :]
            data = _decode_hex(token)
            if data is None:
                return line  # malformed hex -- keep verbatim, do not register
            value: object = data
        else:
            hash_at = after.find("#")
            raw = after if hash_at < 0 else after[:hash_at]
            comment = "" if hash_at < 0 else after[hash_at:]
            trimmed = raw.rstrip(" \t")
            suffix = raw[len(trimmed) :] + comment
            if not trimmed:
                return line
            if kind == _INT:
                try:
                    value = int(trimmed, 0)
                except ValueError:
                    return line
            else:
                value = trimmed

        entry = _KeyEntry(
            canonical, kind, value, indent=indent, key_text=key_text, sep=sep, suffix=suffix
        )
        self._index[canonical] = entry
        return entry

    def _set(self, entry: _KeyEntry) -> None:
        """Add or update a recognised key, keeping source order."""
        existing = self._index.get(entry.canonical)
        if existing is not None:
            existing.value = entry.value
            return
        self._index[entry.canonical] = entry
        self._lines.append(entry)

    # -- identity -----------------------------------------------------------

    @property
    def title(self) -> str | None:
        entry = self._index.get("Title")
        return None if entry is None else str(entry.value)

    def set_title(self, title: str) -> None:
        self._set(_KeyEntry("Title", _STR, title))

    @property
    def description(self) -> str | None:
        entry = self._index.get("Description")
        return None if entry is None else str(entry.value)

    def set_description(self, description: str) -> None:
        self._set(_KeyEntry("Description", _STR, description))

    # -- geometry -----------------------------------------------------------

    def _hex(self, canonical: str) -> bytes | None:
        entry = self._index.get(canonical)
        if entry is None:
            return None
        assert isinstance(entry.value, (bytes, bytearray))
        return bytes(entry.value)

    @property
    def block_size(self) -> int:
        data = self._hex("LBADescriptor")
        if data is not None and len(data) >= 8:
            size = (data[5] << 16) | (data[6] << 8) | data[7]
            if size:
                return size
        return _DEFAULT_BLOCK_SIZE

    @property
    def sectors_per_track(self) -> int:
        data = self._hex("ModePage3")
        if data is not None and len(data) >= 12:
            spt = (data[10] << 8) | data[11]
            if spt:
                return spt
        return _DEFAULT_SECTORS_PER_TRACK

    def _cylinders_heads(self) -> tuple[int, int] | None:
        page0 = self._hex("ModePage0")
        if page0 is not None and len(page0) >= 4:
            return (page0[1] << 8) | page0[2], page0[3]
        page4 = self._hex("ModePage4")
        if page4 is not None and len(page4) >= 6:
            return (page4[3] << 8) | page4[4], page4[5]
        return None

    @property
    def cylinders(self) -> int | None:
        chs = self._cylinders_heads()
        return None if chs is None else chs[0]

    @property
    def heads(self) -> int | None:
        chs = self._cylinders_heads()
        return None if chs is None else chs[1]

    @property
    def geometry(self) -> Geometry:
        """The hard-disc :class:`Geometry` this config describes.

        Raises :class:`BeebScsiConfigError` when neither ``ModePage0`` nor
        ``ModePage4`` records cylinders/heads (the firmware would fall back
        to the ``.dat`` file size, which is not available here).
        """
        chs = self._cylinders_heads()
        if chs is None:
            raise BeebScsiConfigError(
                "no ModePage0 or ModePage4 geometry in .cfg; cannot resolve cylinders/heads"
            )
        cylinders, heads = chs
        if cylinders <= 0 or heads <= 0:
            raise BeebScsiConfigError(
                f"malformed .cfg geometry: {cylinders} cylinders, {heads} heads"
            )
        return winchester_geometry(
            cylinders=cylinders,
            heads=heads,
            sectors_per_track=self.sectors_per_track,
            bytes_per_sector=self.block_size,
        )

    def set_geometry(
        self,
        *,
        cylinders: int,
        heads: int,
        sectors_per_track: int = _DEFAULT_SECTORS_PER_TRACK,
        block_size: int = _DEFAULT_BLOCK_SIZE,
    ) -> None:
        """Write *cylinders*/*heads*/*sectors_per_track* into the mode pages.

        Updates ``LBADescriptor`` (block size), ``ModePage0`` and
        ``ModePage4`` (cylinders/heads, both encodings the firmware reads),
        and ``ModePage3`` (sectors/track and bytes/sector), creating any
        page that is absent.
        """
        if cylinders <= 0 or heads <= 0 or sectors_per_track <= 0:
            raise BeebScsiConfigError(
                f"geometry needs positive cylinders/heads/spt, got "
                f"{cylinders}/{heads}/{sectors_per_track}"
            )
        cyl_hi, cyl_lo = (cylinders >> 8) & 0xFF, cylinders & 0xFF

        lba = bytearray(self._hex("LBADescriptor") or bytes(8))
        lba[5] = (block_size >> 16) & 0xFF
        lba[6] = (block_size >> 8) & 0xFF
        lba[7] = block_size & 0xFF
        self._set(_KeyEntry("LBADescriptor", _HEX, bytes(lba)))

        # Page 0 -- ACB-4000 drive parameter list (the .dsc's replacement).
        self._set(
            _KeyEntry(
                "ModePage0",
                _HEX,
                bytes([0x01, cyl_hi, cyl_lo, heads, 0x00, 0x80, 0x00, 0x80, 0x00, 0x01]),
            )
        )

        mp3 = bytearray(self._hex("ModePage3") or _MODEPAGE3_BASE)
        if len(mp3) < 14:
            mp3 = bytearray(_MODEPAGE3_BASE)
        mp3[10] = (sectors_per_track >> 8) & 0xFF
        mp3[11] = sectors_per_track & 0xFF
        mp3[12] = (block_size >> 8) & 0xFF
        mp3[13] = block_size & 0xFF
        self._set(_KeyEntry("ModePage3", _HEX, bytes(mp3)))

        # Page 4 -- rigid drive geometry parameters.
        self._set(
            _KeyEntry("ModePage4", _HEX, bytes([0x04, 0x04, 0x00, cyl_hi, cyl_lo, heads]))
        )

    # -- serialisation ------------------------------------------------------

    def render(self) -> str:
        """The ``.cfg`` text, ending with a newline."""
        rendered = "\n".join(
            item if isinstance(item, str) else item.render() for item in self._lines
        )
        if not rendered.endswith("\n"):
            rendered += "\n"
        return rendered


def geometry_from_cfg(text: str) -> Geometry:
    """Resolve a hard-disc :class:`Geometry` from ``.cfg`` *text*.

    The ``.cfg`` counterpart of :func:`~oaknut.filesystem.geometry_from_dsc`,
    preferred over it because it carries sectors-per-track. Raises
    :class:`BeebScsiConfigError` on a config without resolvable geometry.
    """
    return BeebScsiConfig.parse(text).geometry

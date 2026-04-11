"""AFS info sector (``AFS0``) — the disc-level header.

Each AFS region carries two identical copies of a 256-byte info
sector describing the disc: at ``sec1 = start_cylinder * spc + 1``
and at ``sec2 = sec1 + spc``. The server uses the redundancy to
recover from single-sector corruption on read. ``wfsinit.partition``
is responsible for writing both copies; the read path verifies they
match and raises :class:`AFSInfoSectorError` if not.

Layout (see ``docs/afs-onwire.md`` §Info sector):

=======  ===========================================================
Offset   Field (from L3V126 Uade02.asm:190-205)
=======  ===========================================================
 0-3     ``MPDRNM`` — magic ``'AFS0'``
 4-19    ``MPSZNM`` — disc name, space-padded (16 bytes)
20-21    ``MPSZNC`` — cylinders per disc (LE)
22-24    ``MPSZNS`` — total sectors per disc (24-bit LE)
25       ``MPSZDN`` — number of physical discs (usually 1)
26-27    ``MPSZSC`` — sectors per cylinder (LE)
28       ``MPSZSB`` — bitmap size in sectors (usually 1)
29       ``MPSZAF`` — addition factor (next physical disc step)
30       ``MPSZDI`` — drive increment (next logical drive step)
31-33    ``MPSZSI`` — SIN of root directory (24-bit LE)
34-35    ``MPSZDT`` — packed creation date
36-37    ``MPSZSS`` — start cylinder of the AFS region
38       — floppy/Winchester flag (Beebmaster p.6; not in Uade02
         but WFSINIT writes it; we treat it as optional on read and
         write 0 = Winchester on output)
=======  ===========================================================

Bytes 39-255 are unused and should be zero. The parser ignores them
so info sectors from any producer round-trip cleanly as long as they
have the fields above correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from oaknut.afs.exceptions import AFSInfoSectorError
from oaknut.afs.types import AfsDate, SystemInternalName

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAGIC = b"AFS0"
INFO_SECTOR_SIZE = 256  # BLKSZE (Uade01.asm:254)

_DISC_NAME_LENGTH = 16  # DNAMLN (Uade02.asm:250)
_MIN_DECODABLE_LENGTH = 38  # Everything up to (but not including) byte 38

# Field offsets
_OFF_MAGIC = 0
_OFF_NAME = 4
_OFF_CYLINDERS = 20
_OFF_TOTAL_SECTORS = 22
_OFF_NUM_DISCS = 25
_OFF_SECTORS_PER_CYLINDER = 26
_OFF_BITMAP_SIZE = 28
_OFF_ADDITION_FACTOR = 29
_OFF_DRIVE_INCREMENT = 30
_OFF_ROOT_SIN = 31
_OFF_DATE = 34
_OFF_START_CYLINDER = 36
_OFF_MEDIA_FLAG = 38

# Media flag values (byte 38)
MEDIA_WINCHESTER = 0
MEDIA_FLOPPY = 1  # Beebmaster p.6 footnote; WFSINIT always writes 0


# ---------------------------------------------------------------------------
# Disc-name helpers
# ---------------------------------------------------------------------------


def _encode_disc_name(name: str) -> bytes:
    """Encode a disc name as 16 space-padded ASCII bytes.

    Enforces the ROM rules: printable ASCII only, no spaces inside
    the name, length 1..16. Spaces are used only as trailing pad.
    """
    if not name:
        raise ValueError("disc name must not be empty")
    if len(name) > _DISC_NAME_LENGTH:
        raise ValueError(f"disc name {name!r} exceeds {_DISC_NAME_LENGTH} characters")
    for ch in name:
        if not (0x21 <= ord(ch) <= 0x7E):
            raise ValueError(
                f"disc name {name!r} contains non-printable or space "
                f"character {ch!r}; only printable ASCII (no spaces) is allowed"
            )
    encoded = name.encode("ascii")
    return encoded.ljust(_DISC_NAME_LENGTH, b" ")


def _decode_disc_name(raw: bytes) -> str:
    """Decode a 16-byte space-padded disc name."""
    if len(raw) != _DISC_NAME_LENGTH:
        raise ValueError(f"disc name must be {_DISC_NAME_LENGTH} bytes, got {len(raw)}")
    return raw.rstrip(b" \x00").decode("ascii")


# ---------------------------------------------------------------------------
# InfoSector dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InfoSector:
    """Parsed form of an AFS info sector.

    Attributes mirror the on-disc fields with friendlier Python types.
    All multi-byte integers are decoded from little-endian. The raw
    bytes can be recovered with :meth:`to_bytes` and will always be
    exactly 256 bytes (one sector).
    """

    disc_name: str
    cylinders: int
    total_sectors: int
    sectors_per_cylinder: int
    root_sin: SystemInternalName
    date: AfsDate
    start_cylinder: int
    num_discs: int = 1
    bitmap_size_sectors: int = 1
    addition_factor: int = 0
    drive_increment: int = 1
    media_flag: int = MEDIA_WINCHESTER

    def __post_init__(self) -> None:
        # Validate the disc name up front; encoding rules are strict.
        _encode_disc_name(self.disc_name)

        if not (0 < self.cylinders <= 0xFFFF):
            raise ValueError(f"cylinders {self.cylinders} outside 1..65535")
        if not (0 < self.total_sectors <= 0xFFFFFF):
            raise ValueError(f"total_sectors {self.total_sectors} outside 1..0xFFFFFF")
        if not (0 < self.sectors_per_cylinder <= 0xFFFF):
            raise ValueError(f"sectors_per_cylinder {self.sectors_per_cylinder} outside 1..65535")
        if not (0 < self.num_discs <= 0xFF):
            raise ValueError(f"num_discs {self.num_discs} outside 1..255")
        if not (1 <= self.bitmap_size_sectors <= 0xFF):
            raise ValueError(f"bitmap_size_sectors {self.bitmap_size_sectors} outside 1..255")
        if not (0 <= self.addition_factor <= 0xFF):
            raise ValueError(f"addition_factor {self.addition_factor} outside 0..255")
        if not (0 <= self.drive_increment <= 0xFF):
            raise ValueError(f"drive_increment {self.drive_increment} outside 0..255")
        if not (0 <= self.root_sin <= 0xFFFFFF):
            raise ValueError(f"root_sin {self.root_sin} outside 0..0xFFFFFF")
        if not (0 <= self.start_cylinder <= 0xFFFF):
            raise ValueError(f"start_cylinder {self.start_cylinder} outside 0..65535")
        if not (0 <= self.media_flag <= 0xFF):
            raise ValueError(f"media_flag {self.media_flag} outside 0..255")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialise to the on-disc 256-byte form."""
        buf = bytearray(INFO_SECTOR_SIZE)
        buf[_OFF_MAGIC : _OFF_MAGIC + 4] = MAGIC
        buf[_OFF_NAME : _OFF_NAME + _DISC_NAME_LENGTH] = _encode_disc_name(self.disc_name)
        buf[_OFF_CYLINDERS : _OFF_CYLINDERS + 2] = self.cylinders.to_bytes(2, "little")
        buf[_OFF_TOTAL_SECTORS : _OFF_TOTAL_SECTORS + 3] = self.total_sectors.to_bytes(3, "little")
        buf[_OFF_NUM_DISCS] = self.num_discs
        buf[_OFF_SECTORS_PER_CYLINDER : _OFF_SECTORS_PER_CYLINDER + 2] = (
            self.sectors_per_cylinder.to_bytes(2, "little")
        )
        buf[_OFF_BITMAP_SIZE] = self.bitmap_size_sectors
        buf[_OFF_ADDITION_FACTOR] = self.addition_factor
        buf[_OFF_DRIVE_INCREMENT] = self.drive_increment
        buf[_OFF_ROOT_SIN : _OFF_ROOT_SIN + 3] = int(self.root_sin).to_bytes(3, "little")
        buf[_OFF_DATE : _OFF_DATE + 2] = self.date.to_bytes()
        buf[_OFF_START_CYLINDER : _OFF_START_CYLINDER + 2] = self.start_cylinder.to_bytes(
            2, "little"
        )
        buf[_OFF_MEDIA_FLAG] = self.media_flag
        return bytes(buf)

    @classmethod
    def from_bytes(cls, data: bytes) -> InfoSector:
        """Parse an info sector from raw bytes.

        The input may be exactly 256 bytes (one sector), shorter but
        at least 38 bytes (the end of the known fields), or longer —
        trailing bytes are ignored. The magic bytes are required.
        """
        if len(data) < _MIN_DECODABLE_LENGTH:
            raise AFSInfoSectorError(
                f"info sector too short: {len(data)} bytes (need at least {_MIN_DECODABLE_LENGTH})"
            )
        if data[_OFF_MAGIC : _OFF_MAGIC + 4] != MAGIC:
            raise AFSInfoSectorError(
                f"bad magic: {bytes(data[_OFF_MAGIC : _OFF_MAGIC + 4])!r} != {MAGIC!r}"
            )

        try:
            disc_name = _decode_disc_name(bytes(data[_OFF_NAME : _OFF_NAME + _DISC_NAME_LENGTH]))
        except (UnicodeDecodeError, ValueError) as exc:
            raise AFSInfoSectorError(f"bad disc name: {exc}") from exc

        try:
            date = AfsDate.from_bytes(bytes(data[_OFF_DATE : _OFF_DATE + 2]))
        except ValueError as exc:
            raise AFSInfoSectorError(f"bad date: {exc}") from exc

        # Media flag is optional — older producers might not write it.
        media_flag = data[_OFF_MEDIA_FLAG] if len(data) > _OFF_MEDIA_FLAG else MEDIA_WINCHESTER

        try:
            return cls(
                disc_name=disc_name,
                cylinders=int.from_bytes(data[_OFF_CYLINDERS : _OFF_CYLINDERS + 2], "little"),
                total_sectors=int.from_bytes(
                    data[_OFF_TOTAL_SECTORS : _OFF_TOTAL_SECTORS + 3], "little"
                ),
                num_discs=data[_OFF_NUM_DISCS],
                sectors_per_cylinder=int.from_bytes(
                    data[_OFF_SECTORS_PER_CYLINDER : _OFF_SECTORS_PER_CYLINDER + 2],
                    "little",
                ),
                bitmap_size_sectors=data[_OFF_BITMAP_SIZE],
                addition_factor=data[_OFF_ADDITION_FACTOR],
                drive_increment=data[_OFF_DRIVE_INCREMENT],
                root_sin=SystemInternalName(
                    int.from_bytes(data[_OFF_ROOT_SIN : _OFF_ROOT_SIN + 3], "little")
                ),
                date=date,
                start_cylinder=int.from_bytes(
                    data[_OFF_START_CYLINDER : _OFF_START_CYLINDER + 2], "little"
                ),
                media_flag=media_flag,
            )
        except ValueError as exc:
            raise AFSInfoSectorError(f"invalid info sector: {exc}") from exc


# ---------------------------------------------------------------------------
# Redundant-copy verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InfoSectorPair:
    """Two copies of an info sector that must agree.

    Used by the read path to validate that both copies parse to the
    same field values (modulo irrelevant trailing padding). Disagreement
    is surfaced as :class:`AFSInfoSectorError`.
    """

    primary: InfoSector
    secondary: InfoSector = field(repr=False)

    def __post_init__(self) -> None:
        if self.primary != self.secondary:
            raise AFSInfoSectorError(
                "info sector copies disagree: "
                f"primary={self.primary!r} secondary={self.secondary!r}"
            )

    @classmethod
    def from_bytes_pair(cls, primary_bytes: bytes, secondary_bytes: bytes) -> InfoSectorPair:
        primary = InfoSector.from_bytes(primary_bytes)
        secondary = InfoSector.from_bytes(secondary_bytes)
        return cls(primary=primary, secondary=secondary)

    @property
    def agreed(self) -> InfoSector:
        """Return the single parsed info sector (primary == secondary)."""
        return self.primary

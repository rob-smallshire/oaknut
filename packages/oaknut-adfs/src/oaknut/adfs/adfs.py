"""ADFS filesystem operations — public API.

Provides ADFS (the filesystem handle), ADFSPath (pathlib-inspired navigation),
and ADFSStat (file/directory metadata).

Example usage:

    with ADFS.from_file("games.adf") as adfs:
        for entry in adfs.root:
            print(f"{entry.name:10s} {entry.stat().length:6d}")

        data = (adfs.root / "Games" / "Elite").read_bytes()
"""

from __future__ import annotations

import mmap
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Union

import oaknut.basic as basic
from oaknut.adfs.directory import (
    ADFS_NAME_GRAMMAR,
    Access,
    ADFSDirectoryFormat,
    NewDirectoryFormat,
    OldDirectoryFormat,
    _ADFSDirectory,
    _ADFSDirectoryEntry,
    _ADFSRawAttributes,
)
from oaknut.adfs.exceptions import (
    ADFSDirectoryError,
    ADFSDirectoryFullError,
    ADFSDirectoryNotEmptyError,
    ADFSEntryExistsError,
    ADFSError,
    ADFSFileLockedError,
    ADFSFormatError,
    ADFSPathError,
    ADFSValidationError,
)
from oaknut.adfs.free_space_map import OldFreeSpaceMap
from oaknut.adfs.new_map import (
    DiscRecord,
    NewMap,
    e_disc_record,
    format_blank_single_zone,
)
from oaknut.discimage.surface import DiscImage, SurfaceSpec
from oaknut.discimage.unified_disc import UnifiedDisc
from oaknut.file import AcornMeta, AcornPath, MetaFormat, resolving_io
from oaknut.file.host_bridge import (
    DEFAULT_EXPORT_META_FORMAT,
    DEFAULT_IMPORT_META_FORMATS,
    export_with_metadata,
    import_with_metadata,
)
from oaknut.file.integrity import assert_no_duplicate_names

if TYPE_CHECKING:
    from oaknut.file import BootOption

#: The name comparator for ADFS — every name equality, lookup and ordering
#: in this module routes through it. See :data:`ADFS_NAME_GRAMMAR`.
_name_key = ADFS_NAME_GRAMMAR.name_key


def _validate_adfs_leaf(name: str) -> None:
    """Validate a *new* leaf name against :data:`ADFS_NAME_GRAMMAR`.

    Applied only when *creating* a name (write, mkdir, rename target) —
    never on navigation or read, so a byte-edited disc whose names break
    these rules still lists and reads. The grammar raises
    :class:`ValueError`; re-raise it as an :class:`ADFSPathError`.
    """
    try:
        ADFS_NAME_GRAMMAR.validate(name)
    except ValueError as exc:
        raise ADFSPathError(str(exc)) from exc


_ADFS_SECTORS_PER_TRACK = 16
_ADFS_BYTES_PER_SECTOR = 256

# Root directory sector address for old map formats. S/M/L place the root
# (an Old directory) at sector 2 (0x200); the D format places its New
# directory at sector 4 (0x400), because its 1024-byte physical sectors push
# the post-map boundary to 0x400. Both address in 256-byte sector units.
_OLD_MAP_ROOT_SECTOR = 2
_D_MAP_ROOT_SECTOR = 4
_OLD_DIR_SECTORS = 5  # Old directory occupies 5 sectors
_OLD_FSM_SECTORS = 2  # Old free space map occupies sectors 0-1


# --- ADFS format constants ---


@dataclass(frozen=True)
class ADFSFormat:
    """ADFS disc format specification."""

    surface_specs: list[SurfaceSpec]
    total_sectors: int
    total_bytes: int
    label: str
    #: Whether this shape uses the New Map (FileCore zoned allocation) rather
    #: than the Old free-space map. Governs which structures ``create`` lays down.
    new_map: bool = False

    def __post_init__(self):
        if not self.surface_specs:
            raise ValueError("At least one surface_spec is required")


def _single_sided_spec(num_tracks: int) -> SurfaceSpec:
    track_size = _ADFS_SECTORS_PER_TRACK * _ADFS_BYTES_PER_SECTOR
    return SurfaceSpec(
        num_tracks=num_tracks,
        sectors_per_track=_ADFS_SECTORS_PER_TRACK,
        bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
        track_zero_offset_bytes=0,
        track_stride_bytes=track_size,
    )


def _interleaved_double_sided_specs(num_tracks: int) -> list[SurfaceSpec]:
    track_size = _ADFS_SECTORS_PER_TRACK * _ADFS_BYTES_PER_SECTOR
    return [
        SurfaceSpec(
            num_tracks=num_tracks,
            sectors_per_track=_ADFS_SECTORS_PER_TRACK,
            bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
            track_zero_offset_bytes=0,
            track_stride_bytes=2 * track_size,
        ),
        SurfaceSpec(
            num_tracks=num_tracks,
            sectors_per_track=_ADFS_SECTORS_PER_TRACK,
            bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
            track_zero_offset_bytes=track_size,
            track_stride_bytes=2 * track_size,
        ),
    ]


def _sequential_double_sided_specs(num_tracks: int) -> list[SurfaceSpec]:
    """Surface specs for a 640K image laid out in linear logical-sector order.

    Some 640K ADFS images are stored sequentially — logical sector N at
    byte N x 256, with no per-track side interleave — rather than in the
    interleaved ``.adl`` layout. Modelled as two sides laid end-to-end,
    which (because each side is exactly 1280 sectors) is byte-identical to
    a flat linear image while still reporting a double-sided geometry.
    """
    track_size = _ADFS_SECTORS_PER_TRACK * _ADFS_BYTES_PER_SECTOR
    side_size = num_tracks * track_size
    return [
        SurfaceSpec(
            num_tracks=num_tracks,
            sectors_per_track=_ADFS_SECTORS_PER_TRACK,
            bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
            track_zero_offset_bytes=0,
            track_stride_bytes=track_size,
        ),
        SurfaceSpec(
            num_tracks=num_tracks,
            sectors_per_track=_ADFS_SECTORS_PER_TRACK,
            bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
            track_zero_offset_bytes=side_size,
            track_stride_bytes=track_size,
        ),
    ]


ADFS_S = ADFSFormat(
    surface_specs=[_single_sided_spec(40)],
    total_sectors=640,
    total_bytes=163840,
    label="S",
)

ADFS_M = ADFSFormat(
    surface_specs=[_single_sided_spec(80)],
    total_sectors=1280,
    total_bytes=327680,
    label="M",
)

ADFS_L = ADFSFormat(
    surface_specs=_interleaved_double_sided_specs(80),
    total_sectors=2560,
    total_bytes=655360,
    label="L",
)

#: The same 640K capacity as :data:`ADFS_L`, but imaged in linear
#: logical-sector order instead of the interleaved ``.adl`` layout.
ADFS_L_SEQUENTIAL = ADFSFormat(
    surface_specs=_sequential_double_sided_specs(80),
    total_sectors=2560,
    total_bytes=655360,
    label="L",
)


def _flat_spec(total_sectors: int) -> SurfaceSpec:
    """A single surface addressing the whole image as linear 256-byte sectors."""
    return SurfaceSpec(
        num_tracks=1,
        sectors_per_track=total_sectors,
        bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
        track_zero_offset_bytes=0,
        track_stride_bytes=total_sectors * _ADFS_BYTES_PER_SECTOR,
    )


#: ADFS D — 800K, Old free-space map but a New directory rooted at sector 4.
#: Modelled as a single linear surface (3200 × 256-byte sectors); the D-format
#: images in circulation are not side-interleaved. Interleaved D layout, like
#: the interleaved/linear split at 640K, is not yet disambiguated.
ADFS_D = ADFSFormat(
    surface_specs=[_flat_spec(3200)],
    total_sectors=3200,
    total_bytes=819200,
    label="D",
)

#: ADFS E — 800K single-zone New Map with New directories. Same linear surface
#: as D (they share a size); the map/directory structure distinguishes them.
ADFS_E = ADFSFormat(
    surface_specs=[_flat_spec(3200)],
    total_sectors=3200,
    total_bytes=819200,
    label="E",
    new_map=True,
)

_ADFS_FORMATS_BY_SIZE = {
    ADFS_S.total_bytes: ADFS_S,
    ADFS_M.total_bytes: ADFS_M,
    ADFS_L.total_bytes: ADFS_L,
    ADFS_D.total_bytes: ADFS_D,
}


# The disc-image filename extensions ADFS owns. Floppy extensions map
# to a fixed ADFSFormat that ``disc create`` lays down directly; the
# ``None`` entries are recognised as ADFS for reading but cannot be
# created from the extension alone — ``.adf`` because its size is
# ambiguous (S / M / L), ``.dat`` because a hard disc needs an
# explicit capacity. This is the single source of truth for "which
# extensions mean ADFS"; the CLI's filing-system detection derives
# its ADFS extension set from these keys.
IMAGE_FORMAT_BY_EXTENSION: dict[str, "ADFSFormat | None"] = {
    ".adf": None,
    ".ads": ADFS_S,
    ".adm": ADFS_M,
    ".adl": ADFS_L,
    ".dat": None,
}


# --- Hard disc (.dat/.dsc) support ---

_DSC_SIZE = 22
_SCSI_SECTORS_PER_TRACK = 33


@dataclass(frozen=True)
class ADFSGeometry:
    """Authoritative disc geometry.

    For hard disc images this comes from the ``.dsc`` sidecar file.
    For floppies it is derived from the format constants (ADFS_S/M/L).
    """

    cylinders: int
    heads: int
    sectors_per_track: int = _SCSI_SECTORS_PER_TRACK

    @property
    def sectors_per_cylinder(self) -> int:
        """Sectors per cylinder (heads x sectors per track)."""
        return self.heads * self.sectors_per_track

    @property
    def total_sectors(self) -> int:
        """Total sectors on the disc."""
        return self.cylinders * self.sectors_per_cylinder


_FLOPPY_GEOMETRY = {
    ADFS_S.total_bytes: ADFSGeometry(cylinders=40, heads=1, sectors_per_track=16),
    ADFS_M.total_bytes: ADFSGeometry(cylinders=80, heads=1, sectors_per_track=16),
    ADFS_L.total_bytes: ADFSGeometry(cylinders=80, heads=2, sectors_per_track=16),
    # D: 5 × 1024-byte sectors/track = 20 × 256-byte sectors, 80 tracks, 2 sides.
    ADFS_D.total_bytes: ADFSGeometry(cylinders=80, heads=2, sectors_per_track=20),
}


def _parse_dsc(filepath: Union[str, PathLike]) -> ADFSGeometry:
    """Parse a 22-byte .dsc sidecar file.

    The .dsc file contains SCSI MODE SENSE data with disc geometry:
      Bytes 13–14: cylinders (big-endian 16-bit)
      Byte 15: number of heads
      Sectors per track is always 33.
    """
    data = Path(filepath).read_bytes()
    if len(data) != _DSC_SIZE:
        raise ADFSError(f"DSC file should be {_DSC_SIZE} bytes, got {len(data)}")
    return ADFSGeometry(
        cylinders=(data[13] << 8) | data[14],
        heads=data[15],
    )


def _hard_disc_format(geometry: ADFSGeometry, dat_size_bytes: int) -> ADFSFormat:
    """Create an ADFSFormat for a hard disc image from geometry and file size.

    ADFS addresses hard discs using linear SCSI LBA — sector N is at
    byte offset N×256 in the .dat file.  The CHS geometry from the .dsc
    file describes the physical drive but is **not** used for ADFS
    sector addressing: the 22-byte ``.dsc`` carries cylinders + heads
    only and ``_parse_dsc`` therefore always reports SPT=33 regardless
    of the actual geometry, so any addressing scheme that depended on
    SPT would silently truncate the addressable surface for non-SCSI
    interfaces (e.g. the RetroClinic Data Centre's IDE 4×64 layout).

    We model the image as a single flat surface matching ADFS's linear
    view — same shape as :meth:`ADFS.from_buffer` synthesises when no
    ``.dsc`` is present.  The geometry is recorded on the returned
    :class:`ADFSGeometry` for metadata (e.g. ``ADFS.geometry``) but
    does not affect the addressable extent.
    """
    if dat_size_bytes % _ADFS_BYTES_PER_SECTOR != 0:
        raise ADFSError(
            f"Hard disc image size ({dat_size_bytes}) is not a multiple "
            f"of the sector size ({_ADFS_BYTES_PER_SECTOR})"
        )

    total_sectors = dat_size_bytes // _ADFS_BYTES_PER_SECTOR
    del geometry  # intentionally unused — the file size is the source of truth

    spec = SurfaceSpec(
        num_tracks=1,
        sectors_per_track=total_sectors,
        bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
        track_zero_offset_bytes=0,
        track_stride_bytes=dat_size_bytes,
    )

    return ADFSFormat(
        surface_specs=[spec],
        total_sectors=total_sectors,
        total_bytes=dat_size_bytes,
        label="HardDisc",
    )


def geometry_for_capacity(
    capacity_bytes: int,
    *,
    heads: int = 4,
    sectors_per_track: int = _SCSI_SECTORS_PER_TRACK,
) -> ADFSGeometry:
    """Compute a disc geometry that meets or exceeds a requested capacity.

    Returns a ``ADFSGeometry`` with the minimum number of cylinders
    needed to provide at least *capacity_bytes* of storage.

    Args:
        capacity_bytes: Minimum disc capacity in bytes.
        heads: Number of heads (default 4).
        sectors_per_track: Sectors per track (default 33).

    Returns:
        Geometry with cylinders computed from the capacity.

    Raises:
        ValueError: If capacity_bytes is not positive.
    """
    if capacity_bytes <= 0:
        raise ValueError(f"capacity_bytes must be positive, got {capacity_bytes}")

    bytes_per_cylinder = heads * sectors_per_track * _ADFS_BYTES_PER_SECTOR
    cylinders = -(-capacity_bytes // bytes_per_cylinder)  # ceiling division
    return ADFSGeometry(
        cylinders=cylinders,
        heads=heads,
        sectors_per_track=sectors_per_track,
    )


def write_dsc(filepath: Union[str, PathLike], geometry: ADFSGeometry) -> None:
    """Write a 22-byte ``.dsc`` sidecar file with SCSI disc geometry.

    The sidecar carries cylinders/heads/sectors-per-track for a hard
    disc image so :func:`ADFS.from_file` can address sectors via CHS.
    """
    _write_dsc(filepath, geometry)


def _write_dsc(filepath: Union[str, PathLike], geometry: ADFSGeometry) -> None:
    """Write a 22-byte .dsc sidecar file with SCSI disc geometry."""
    data = bytearray(_DSC_SIZE)
    data[3] = 0x08  # Speed class
    data[10] = 0x01  # Removable flag
    data[12] = 0x01  # Stepping rate
    data[13] = (geometry.cylinders >> 8) & 0xFF  # Cylinders high
    data[14] = geometry.cylinders & 0xFF  # Cylinders low
    data[15] = geometry.heads  # Heads
    data[17] = 0x80  # RWCC low
    data[19] = 0x80  # Landing zone
    data[21] = 0x01
    Path(filepath).write_bytes(data)


# --- Public value type ---


@dataclass(frozen=True)
class ADFSStat:
    """File/directory metadata, analogous to os.stat_result.

    Conforms to :class:`oaknut.file.Stat` — :attr:`access` is
    synthesised from the per-owner / per-public bits, and
    :attr:`date` is always ``None`` (ADFS dates live at the
    directory level and are not currently surfaced here).
    """

    length: int
    load_address: int
    exec_address: int
    locked: bool
    owner_read: bool
    owner_write: bool
    owner_execute: bool
    public_read: bool
    public_write: bool
    public_execute: bool
    is_directory: bool

    @property
    def access(self) -> Access:
        """Access flags as an ``Access`` IntFlag, suitable for ``chmod()``."""
        flags = Access(0)
        if self.owner_read:
            flags |= Access.R
        if self.owner_write:
            flags |= Access.W
        if self.owner_execute:
            flags |= Access.E
        if self.locked:
            flags |= Access.L
        if self.public_read:
            flags |= Access.PR
        if self.public_write:
            flags |= Access.PW
        return flags

    @property
    def date(self) -> None:
        """ADFS does not surface per-entry dates here — always ``None``."""
        return None


def _coerce_access_to_locked(access: "Access | None") -> bool:
    """Project the canonical ``access`` value down to ``locked: bool``.

    write_bytes only sets the locked bit at the catalogue-write
    layer; richer flags (R/W/E/PR/PW) are applied later via
    :meth:`chmod`. ``None`` (the default) maps to unlocked; an
    :class:`Access` value is masked against ``Access.L``.
    """
    if access is None:
        return False
    return bool(int(access) & int(Access.L))


def _entry_to_stat(entry: _ADFSDirectoryEntry) -> ADFSStat:
    """Convert an internal directory entry to a public ADFSStat."""
    return ADFSStat(
        length=entry.length,
        load_address=entry.load_address,
        exec_address=entry.exec_address,
        locked=entry.attributes.locked,
        owner_read=entry.attributes.owner_read,
        owner_write=entry.attributes.owner_write,
        owner_execute=entry.attributes.owner_execute,
        public_read=entry.attributes.public_read,
        public_write=entry.attributes.public_write,
        public_execute=entry.attributes.public_execute,
        is_directory=entry.attributes.directory,
    )


# --- ADFSPath ---


class ADFSPath(AcornPath):
    EntryExistsError = ADFSEntryExistsError
    DirectoryError = ADFSPathError
    supports_title = True

    """A path within an ADFS filesystem, inspired by pathlib.Path.

    ADFSPath objects are lightweight handles that reference an ADFS
    filesystem and a normalised absolute path string. They do not
    cache directory contents, so they always reflect the current
    state of the disc image.

    Navigation uses the ``/`` operator::

        games = adfs.root / "Games"
        elite = games / "Elite"

    Iterate over directory contents::

        for child in games:
            print(child.name)

    Read file data::

        data = elite.read_bytes()
    """

    def __init__(self, adfs: ADFS, path: str):
        self._adfs = adfs
        self._path = path

    # --- Navigation ---

    def _join_name(self, name: str) -> ADFSPath:
        if name == "$":
            # Acorn absolute-path marker — reset to root.
            return ADFSPath(self._adfs, "$")
        if self._path == "$":
            return ADFSPath(self._adfs, f"$.{name}")
        return ADFSPath(self._adfs, f"{self._path}.{name}")

    def _root(self) -> ADFSPath:
        return ADFSPath(self._adfs, "$")

    def _root_parts(self) -> tuple[str, ...]:
        return ("$",)

    @property
    def parent(self) -> ADFSPath:
        """Parent directory."""
        parts = self._path.split(".")
        if len(parts) <= 1:
            return self  # Root's parent is itself
        return ADFSPath(self._adfs, ".".join(parts[:-1]))

    @property
    def name(self) -> str:
        """Final component of the path."""
        return self._path.split(".")[-1]

    @property
    def parts(self) -> tuple[str, ...]:
        """Path components as a tuple, e.g. ``("$", "Games", "Elite")``."""
        return tuple(self._path.split("."))

    @property
    def path(self) -> str:
        """Full path string, e.g. ``"$.Games.Elite"``."""
        return self._path

    # --- Querying ---

    @resolving_io
    def exists(self) -> bool:
        """Check whether this path exists on disc."""
        if self._path == "$":
            return True
        try:
            self._resolve()
            return True
        except ADFSPathError:
            return False

    @resolving_io
    def is_dir(self) -> bool:
        """Check whether this path is a directory."""
        if self._path == "$":
            return True
        try:
            _, entry = self._resolve()
            return entry.is_directory
        except ADFSPathError:
            return False

    @resolving_io
    def is_file(self) -> bool:
        """Check whether this path is a file (not a directory)."""
        if self._path == "$":
            return False
        try:
            _, entry = self._resolve()
            return not entry.is_directory
        except ADFSPathError:
            return False

    @resolving_io
    def stat(self) -> ADFSStat:
        """Return metadata for this path.

        Raises:
            ADFSPathError: If the path does not exist.
        """
        if self._path == "$":
            return ADFSStat(
                length=self._adfs._dir_format.size_in_bytes,
                load_address=0,
                exec_address=0,
                locked=False,
                owner_read=True,
                owner_write=True,
                owner_execute=False,
                public_read=True,
                public_write=False,
                public_execute=False,
                is_directory=True,
            )
        _, entry = self._resolve()
        return _entry_to_stat(entry)

    @property
    def title(self) -> str:
        """Directory title (up to 19 characters).

        Distinct from the directory name: the name is the structural
        component used in paths; the title is a human-readable label
        stored inside the directory block.

        Raises:
            ADFSPathError: If this path is a file, not a directory.
        """
        directory = self._resolve_as_directory()
        return directory.title

    @title.setter
    def title(self, value: str) -> None:
        """Set directory title.

        Raises:
            ADFSPathError: If this path is a file, not a directory.
        """
        if self._path == "$":
            disc_address = self._adfs._root_address
        else:
            _, entry = self._resolve()
            if not entry.is_directory:
                raise ADFSPathError(f"'{self._path}' is not a directory")
            disc_address = entry.indirect_disc_address

        directory = self._adfs._read_directory_at(disc_address)
        updated = _ADFSDirectory(
            name=directory.name,
            title=value,
            parent_address=directory.parent_address,
            disc_address=directory.disc_address,
            entries=directory.entries,
            sequence_number=directory.sequence_number,
            signature=directory.signature,
        )
        self._adfs._write_directory_at(updated, disc_address)

    # --- Directory operations ---

    @resolving_io
    def iterdir(self) -> Iterator[ADFSPath]:
        """Iterate over directory contents.

        Raises:
            ADFSPathError: If this path is not a directory or doesn't exist.
        """
        directory = self._resolve_as_directory()
        for entry in directory.entries:
            yield self / entry.name

    # --- File operations ---

    @resolving_io
    def read_bytes(self) -> bytes:
        """Read file contents.

        Raises:
            ADFSPathError: If the path doesn't exist or is a directory.
        """
        if self._path == "$":
            raise ADFSPathError("Cannot read root directory as file")
        _, entry = self._resolve()
        if entry.is_directory:
            raise ADFSPathError(f"'{self._path}' is a directory, not a file")
        return self._adfs._read_file_data(entry)

    @resolving_io
    def read_basic(self) -> str:
        """Read a BBC BASIC program and return its detokenised source.

        Composes :meth:`read_bytes` with
        :func:`oaknut.dfs.basic.detokenise`. Never compose a BASIC
        program with :meth:`read_text` — tokenised BASIC is bytecode,
        not text, and decoding it through a character codec will
        produce garbage.

        Raises:
            ADFSPathError: If the path doesn't exist or is a directory.
            DetokeniseError: If the stored program is not valid tokenised
                BBC BASIC.
        """
        return basic.detokenise(self.read_bytes())

    @resolving_io
    def write_bytes(
        self,
        data: bytes,
        *,
        load_address: int = 0,
        exec_address: int = 0,
        access: "Access | None" = None,
        date: object = None,
    ) -> None:
        """Write file contents, creating or overwriting the file.

        ``access`` accepts a :class:`oaknut.file.Access` value, or
        ``None`` for the filesystem default (unlocked + owner R+W).
        Only the locked bit is honoured at the catalogue-write layer;
        richer flags (owner R/W/E, public R/W) must be applied via
        :meth:`chmod` after the write.

        ``date`` is accepted for cross-filesystem signature uniformity
        but silently ignored at this layer.

        Args:
            data: File contents.
            load_address: Load address (default 0).
            exec_address: Execution address (default 0).

        Raises:
            ADFSPathError: If this path is the root directory.
            ADFSDiscFullError: If the disc has insufficient free space.
            ADFSDirectoryFullError: If the parent directory is full.
        """
        del date  # accepted for signature uniformity only

        locked_val = _coerce_access_to_locked(access)

        if self._path == "$":
            raise ADFSPathError("Cannot write to root directory")

        parts = self._path.split(".")
        if len(parts) < 2 or parts[0] != "$":
            raise ADFSPathError(f"Invalid path: {self._path!r}")
        _validate_adfs_leaf(parts[-1])

        self._adfs._write_file(
            parts,
            data,
            load_address,
            exec_address,
            locked_val,
        )

    @resolving_io
    def write_basic(
        self,
        source: str,
        *,
        load_address: int = basic.BBC_BASIC_LOAD_ADDRESS,
        exec_address: int = 0,
        access: "Access | None" = None,
    ) -> None:
        """Write a BBC BASIC program, tokenising the source first.

        Composes :func:`oaknut.dfs.basic.tokenise` with
        :meth:`write_bytes`. Defaults the load address to the BBC
        Micro's canonical ``0x1900``; pass
        :data:`oaknut.dfs.basic.ELECTRON_BASIC_LOAD_ADDRESS` for
        Electron programs.

        Args:
            source: BBC BASIC source text.
            load_address: Load address (default ``0x1900``).
            exec_address: Execution address (default 0).
            access: Access flags (see :meth:`write_bytes`).

        Raises:
            ADFSPathError: If this path is the root directory.
            ADFSDiscFullError: If the disc has insufficient free space.
            ADFSDirectoryFullError: If the parent directory is full.
            TokeniseError: If the source is not valid BBC BASIC.
        """
        self.write_bytes(
            basic.tokenise(source),
            load_address=load_address,
            exec_address=exec_address,
            access=access,
        )

    @resolving_io
    def unlink(self) -> None:
        """Delete this file.

        Raises:
            ADFSPathError: If the path is root, doesn't exist, or is a directory.
            ADFSFileLockedError: If the file is locked.
        """
        if self._path == "$":
            raise ADFSPathError("Cannot unlink root directory")
        self._adfs._unlink_file(self._path.split("."))

    @resolving_io
    def mkdir(self, *, parents: bool = False, exist_ok: bool = False) -> None:
        """Create a new directory at this path.

        Mirrors :meth:`pathlib.Path.mkdir`.

        Args:
            parents: If ``True``, missing intermediate directories are
                created. Default ``False`` raises when any ancestor is
                absent.
            exist_ok: If ``True``, do not raise when this path already
                resolves to a directory. A non-directory at the path
                still raises. Default ``False``.

        Raises:
            ADFSPathError: If the path is root, parent is not found
                (and ``parents`` is ``False``), or already exists
                as a file. Also when ``exist_ok`` is ``False`` and
                the path already exists.
            ADFSDiscFullError: If the disc has insufficient free space.
            ADFSDirectoryFullError: If the parent directory is full.
        """
        if self._path == "$":
            raise ADFSPathError("Cannot mkdir root directory")
        _validate_adfs_leaf(self._path.split(".")[-1])

        if parents:
            parent = self.parent
            if not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)

        if exist_ok and self.exists():
            if self.is_dir():
                return
            raise ADFSPathError(f"'{self._path}' already exists as a file")

        self._adfs._mkdir(self._path.split("."))

    @resolving_io
    def rmdir(self) -> None:
        """Remove an empty directory.

        Raises:
            ADFSPathError: If the path is root, doesn't exist, is not a
                directory, or is not empty.
            ADFSFileLockedError: If the directory is locked.
        """
        if self._path == "$":
            raise ADFSPathError("Cannot rmdir root directory")
        self._adfs._rmdir(self._path.split("."))

    @resolving_io
    def rename(self, target: Union[str, ADFSPath]) -> ADFSPath:
        """Rename this file or directory, returning the new path.

        Moving across directories is supported.

        Args:
            target: New path (ADFSPath or string like ``"$.NewName"``).

        Returns:
            ADFSPath for the new location.

        Raises:
            ADFSPathError: If this path doesn't exist, or target already exists.
        """
        if self._path == "$":
            raise ADFSPathError("Cannot rename root directory")

        if isinstance(target, ADFSPath):
            target_path = target._path
        else:
            target_path = target

        target_parts = target_path.split(".")
        _validate_adfs_leaf(target_parts[-1])
        self._adfs._rename(self._path.split("."), target_parts)
        return ADFSPath(self._adfs, target_path)

    @resolving_io
    def lock(self) -> None:
        """Lock this file.

        Raises:
            ADFSPathError: If the path is root or doesn't exist.
        """
        if self._path == "$":
            raise ADFSPathError("Cannot lock root directory")
        self._adfs._set_locked(self._path.split("."), True)

    @resolving_io
    def unlock(self) -> None:
        """Unlock this file.

        Raises:
            ADFSPathError: If the path is root or doesn't exist.
        """
        if self._path == "$":
            raise ADFSPathError("Cannot unlock root directory")
        self._adfs._set_locked(self._path.split("."), False)

    @resolving_io
    def chmod(self, access: int) -> None:
        """Set access attributes, replacing the current ones.

        Uses the ``Access`` IntFlag enum::

            from oaknut.adfs.directory import Access
            path.chmod(Access.R | Access.W | Access.L)

        Only the owner R, W, L, and E attributes are affected.
        Public/private NFS attributes are preserved.

        Args:
            access: Combination of ``Access`` flags.

        Raises:
            ADFSPathError: If the path is root or doesn't exist.
        """
        if self._path == "$":
            raise ADFSPathError("Cannot chmod root directory")
        self._adfs._chmod(self._path.split("."), access)

    @resolving_io
    def set_load_address(self, address: int) -> None:
        """Set the load address without rewriting the file data.

        Raises:
            ADFSPathError: If the path doesn't exist.
        """
        self._adfs._set_load_address(self._path.split("."), address)

    @resolving_io
    def set_exec_address(self, address: int) -> None:
        """Set the exec address without rewriting the file data.

        Raises:
            ADFSPathError: If the path doesn't exist.
        """
        self._adfs._set_exec_address(self._path.split("."), address)

    # --- Host filesystem transfer ---

    def export_file(
        self,
        target_filepath: Union[str, PathLike],
        *,
        meta_format: MetaFormat | None = DEFAULT_EXPORT_META_FORMAT,
        owner: int = 0,
    ) -> Path:
        """Export file to host filesystem, emitting Acorn metadata.

        Args:
            target_filepath: Destination path on the host.
            meta_format: How to encode metadata. Defaults to traditional
                INF sidecar. Pass ``None`` to write only the data.
                Filename-encoded formats rewrite the target filename.
            owner: Econet owner ID, used only by PiEconetBridge formats.

        Returns:
            The actual path that was written. Equal to *target_filepath*
            except for filename-encoded formats.
        """
        _, entry = self._resolve()
        data = self.read_bytes()
        meta = AcornMeta(
            load_address=entry.load_address,
            exec_address=entry.exec_address,
            access=int(_entry_to_stat(entry).access),
        )
        return export_with_metadata(
            data,
            Path(target_filepath),
            meta,
            meta_format=meta_format,
            owner=owner,
            filename=self.name,
        )

    def import_file(
        self,
        source_filepath: Union[str, PathLike],
        *,
        meta_formats: Sequence[MetaFormat] = DEFAULT_IMPORT_META_FORMATS,
    ) -> None:
        """Import a file from the host filesystem.

        The ADFS filename is taken from this ``ADFSPath``, not from the
        source file or any sidecar. Metadata is resolved by trying
        *meta_formats* in order; the first reader to match wins. The
        full Acorn attribute byte (R/W/E/L/PR/PW) is applied via
        :meth:`chmod` after the data has been written, so owner-execute
        and public permissions round-trip losslessly via
        ``MetaFormat.INF_PIEB`` or either xattr format.

        Args:
            source_filepath: Path to the source file on the host.
            meta_formats: Ordered cascade of metadata schemes to try.
                Defaults to ``DEFAULT_IMPORT_META_FORMATS``.
        """
        source = Path(source_filepath)
        data = source.read_bytes()
        _, _, meta = import_with_metadata(source, meta_formats=meta_formats)

        load_address = meta.load_address or 0
        exec_address = meta.exec_address or 0
        access = meta.access

        self.write_bytes(
            data,
            load_address=load_address,
            exec_address=exec_address,
            access=bool((access or 0) & int(Access.L)),
        )

        # If the resolved metadata carries richer Acorn attributes than
        # the write_bytes locked flag covers (owner R/W/E, public R/W),
        # apply them via chmod so they actually land in the directory
        # entry. write_bytes has set a default R|W for the owner via
        # the internal _write_file path, so a no-op chmod is harmless.
        if access is not None:
            self.chmod(access)

    # --- Protocols ---

    def __str__(self) -> str:
        return self._path

    def __repr__(self) -> str:
        return f"ADFSPath({self._path!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ADFSPath):
            return NotImplemented
        return self._adfs is other._adfs and _name_key(self._path) == _name_key(other._path)

    def __hash__(self) -> int:
        return hash(_name_key(self._path))

    @resolving_io
    def __contains__(self, name: str) -> bool:
        """Check if *name* exists in this directory."""
        directory = self._resolve_as_directory()
        return directory.find(name) is not None

    # --- Internal helpers ---

    def _resolve(self) -> tuple[_ADFSDirectory, _ADFSDirectoryEntry]:
        """Navigate the directory tree to find this path's entry.

        Returns:
            (parent_directory, entry) tuple.

        Raises:
            ADFSPathError: If the path doesn't exist.
        """
        parts = self._path.split(".")
        if not parts or parts[0] != "$":
            raise ADFSPathError(f"Path must start with '$': {self._path!r}")

        if len(parts) == 1:
            raise ADFSPathError("Cannot resolve root directory as an entry")

        current_dir = self._adfs._read_root_directory()

        for i, component in enumerate(parts[1:], 1):
            entry = current_dir.find(component)
            if entry is None:
                partial = ".".join(parts[: i + 1])
                raise ADFSPathError(f"'{component}' not found in '{partial}'")

            if i < len(parts) - 1:
                # Need to descend into this directory
                if not entry.is_directory:
                    partial = ".".join(parts[: i + 1])
                    raise ADFSPathError(f"'{partial}' is not a directory")
                current_dir = self._adfs._read_directory_at(entry.indirect_disc_address)

        return current_dir, entry

    def _resolve_as_directory(self) -> _ADFSDirectory:
        """Resolve this path as a directory.

        Raises:
            ADFSPathError: If the path is not a directory.
        """
        if self._path == "$":
            return self._adfs._read_root_directory()

        parent_dir, entry = self._resolve()
        if not entry.is_directory:
            raise ADFSPathError(f"'{self._path}' is not a directory")
        return self._adfs._read_directory_at(entry.indirect_disc_address)


# --- ADFS filesystem handle ---


def _detect_format(buffer_size: int) -> ADFSFormat:
    """Detect ADFS format from image file size.

    Raises:
        ADFSError: If the size doesn't match any known ADFS floppy format.
    """
    fmt = _ADFS_FORMATS_BY_SIZE.get(buffer_size)
    if fmt is None:
        sizes = ", ".join(f"{f.total_bytes} ({f.label})" for f in _ADFS_FORMATS_BY_SIZE.values())
        raise ADFSError(f"Unrecognised ADFS image size: {buffer_size} bytes. Expected {sizes}.")
    return fmt


def _directory_tree_traverses(buffer: memoryview, fmt: ADFSFormat) -> bool:
    """Whether the whole directory tree parses under a candidate layout.

    The two 640K layouts (interleaved ``.adl`` and linear) differ only
    once a directory's sectors cross a track boundary, so the cheapest
    reliable discriminator is to walk every directory and see which layout
    keeps producing valid 'Hugo'/'Nick' signatures and matching tails.
    """
    geom = _FLOPPY_GEOMETRY.get(len(buffer))
    try:
        adfs = ADFS._from_buffer_with_format(buffer, fmt, geom)
    except ADFSDirectoryError:
        return False
    return not adfs._directory_tree_errors()


def _disambiguate_640k_layout(
    buffer: memoryview, *, prefer_sequential: bool = False
) -> ADFSFormat:
    """Choose the interleaved or linear 640K layout by content.

    Both candidates are tried; the one whose directory tree traverses
    cleanly wins. When both traverse (a disc whose every directory lives
    in track 0 side 0, where the layouts coincide and so reads are
    byte-identical) the choice is cosmetic, and *prefer_sequential* — set
    from the image's extension as a tiebreak — decides. The interleaved
    ``.adl`` layout remains the default.
    """
    ordered = (
        (ADFS_L_SEQUENTIAL, ADFS_L) if prefer_sequential else (ADFS_L, ADFS_L_SEQUENTIAL)
    )
    for fmt in ordered:
        if _directory_tree_traverses(buffer, fmt):
            return fmt
    # Neither traverses — keep the historical default and let the normal
    # parse path surface a precise error.
    return ordered[0]


def _initialise_old_free_space_map(
    unified: UnifiedDisc,
    total_sectors: int,
    boot_option: int = 0,
) -> None:
    """Write an empty old-format free space map to sectors 0–1."""
    from oaknut.adfs.free_space_map import _calculate_old_map_checksum

    data = unified.sector_range(0, 2)

    # Single free space entry: everything after the root directory
    used_sectors = _OLD_FSM_SECTORS + _OLD_DIR_SECTORS  # 7
    free_start = used_sectors
    free_length = total_sectors - used_sectors

    # FreeStart[0] at 0x000 (3 bytes LE)
    data[0x000] = free_start & 0xFF
    data[0x001] = (free_start >> 8) & 0xFF
    data[0x002] = (free_start >> 16) & 0xFF

    # FreeLen[0] at 0x100 (3 bytes LE)
    data[0x100] = free_length & 0xFF
    data[0x101] = (free_length >> 8) & 0xFF
    data[0x102] = (free_length >> 16) & 0xFF

    # OldSize at 0x0FC (3 bytes LE)
    data[0x0FC] = total_sectors & 0xFF
    data[0x0FD] = (total_sectors >> 8) & 0xFF
    data[0x0FE] = (total_sectors >> 16) & 0xFF

    # Boot option at 0x1FD
    data[0x1FD] = boot_option

    # FreeEnd pointer at 0x1FE (1 entry × 3 bytes)
    data[0x1FE] = 3

    # Calculate and write checksums
    data[0x0FF] = _calculate_old_map_checksum(data, 0x000)
    data[0x1FF] = _calculate_old_map_checksum(data, 0x100)


def _initialise_old_root_directory(
    unified: UnifiedDisc,
    title: str = "",
) -> None:
    """Write an empty old-format root directory to sectors 2–6."""
    data = unified.sector_range(_OLD_MAP_ROOT_SECTOR, _OLD_DIR_SECTORS)

    # Header
    data[0x00] = 0  # StartMasSeq
    data[0x01:0x05] = b"Hugo"  # StartName

    # Zero the entries area — required when reinitialising an
    # existing directory (e.g. during compact).
    for i in range(0x05, 0x4CB):
        data[i] = 0

    # Tail at offset 0x4CB
    tail = 0x4CB
    data[tail] = 0x00  # OldDirLastMark

    # Directory name: "$" + null padding
    data[tail + 1] = ord("$")
    # Bytes tail+2 through tail+10 are zero (already)

    # Parent address: root's parent is itself (sector 2 = 0x000002)
    data[tail + 11] = _OLD_MAP_ROOT_SECTOR & 0xFF
    data[tail + 12] = (_OLD_MAP_ROOT_SECTOR >> 8) & 0xFF
    data[tail + 13] = (_OLD_MAP_ROOT_SECTOR >> 16) & 0xFF

    # Title (19 bytes, null-terminated)
    title_bytes = title.encode("ascii")[:19]
    for i, b in enumerate(title_bytes):
        data[tail + 14 + i] = b

    # Reserved (14 bytes): already zero

    # EndMasSeq
    data[tail + 47] = 0  # Must match StartMasSeq
    # EndName
    data[tail + 48 : tail + 52] = b"Hugo"
    # DirCheckByte: reserved, must be zero
    data[tail + 52] = 0x00


def _initialise_new_map_blank(
    unified: UnifiedDisc,
    total_sectors: int,
    title: str,
    boot_option: int,
) -> DiscRecord:
    """Lay down a blank single-zone New Map and empty "Nick" root directory.

    The New Map counterpart of :func:`_initialise_old_free_space_map` plus
    :func:`_initialise_old_root_directory`. Returns the disc record so the
    caller can build the :class:`NewMap` over the finished image. Currently
    ADFS E only (the single-zone shape).
    """
    dr = e_disc_record(title, boot_option=boot_option)
    dir_format = NewDirectoryFormat()

    full = unified.sector_range(0, total_sectors)
    root_address = format_blank_single_zone(full, dr, dir_format.size_in_bytes)

    root_dir = _ADFSDirectory(
        name="$",
        title=title,
        parent_address=dr.root,
        disc_address=dr.root,
        entries=(),
        sequence_number=0,
        signature=b"Nick",
    )
    root_data = unified.sector_range(
        root_address // _ADFS_BYTES_PER_SECTOR, dir_format.size_in_sectors
    )
    dir_format.serialize(root_dir, root_data)
    return dr


@contextmanager
def _create_image_file(
    filepath: Path,
    fmt: ADFSFormat,
    geometry: ADFSGeometry,
    title: str,
    boot_option: int,
) -> Iterator[ADFS]:
    """Write a blank image file, initialise ADFS structures, and yield an ADFS handle."""
    with open(filepath, "wb") as f:
        f.write(b"\x00" * fmt.total_bytes)

    with open(filepath, "r+b") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_WRITE)
        buffer = memoryview(mm)
        disc_image = DiscImage(buffer, fmt.surface_specs)
        unified = UnifiedDisc(disc_image)

        if fmt.new_map:
            disc_record = _initialise_new_map_blank(
                unified, fmt.total_sectors, title, boot_option
            )
            new_map = _new_map_over(unified, disc_record)
            adfs = ADFS(
                unified, NewDirectoryFormat(), None, geometry, disc_record.root, new_map=new_map
            )
        else:
            _initialise_old_free_space_map(unified, fmt.total_sectors, boot_option)
            _initialise_old_root_directory(unified, title)

            map_data = unified.sector_range(0, 2)
            fsm = OldFreeSpaceMap(map_data)
            adfs = ADFS(unified, OldDirectoryFormat(), fsm, geometry)
        try:
            yield adfs
        finally:
            adfs.close()
            mm.flush()


def _floppy_format_from_extension(ext: str) -> ADFSFormat:
    """Pick a floppy :class:`ADFSFormat` from a lowercase extension.

    Recognises ``.ads``, ``.adm`` and ``.adl``. Anything else —
    including the historically-ambiguous ``.adf`` (used for both S
    and M sizes) — raises :class:`ADFSFormatError`.
    """
    table = {".ads": ADFS_S, ".adm": ADFS_M, ".adl": ADFS_L}
    if ext not in table:
        raise ADFSFormatError(
            f"cannot pick a default ADFS format for extension {ext!r}; "
            "pass adfs_format= explicitly (ADFS_S, ADFS_M, or ADFS_L)"
        )
    return table[ext]


@contextmanager
def _create_floppy_file(
    filepath: Path,
    *,
    adfs_format: ADFSFormat,
    title: str,
    boot_option: int,
) -> Iterator[ADFS]:
    """Create a floppy disc image file."""
    if adfs_format is None:
        raise ValueError("Floppy disc images require an adfs_format (ADFS_S, ADFS_M, or ADFS_L)")
    geom = _FLOPPY_GEOMETRY.get(adfs_format.total_bytes)
    if geom is None:
        spec = adfs_format.surface_specs[0]
        geom = ADFSGeometry(
            cylinders=spec.num_tracks,
            heads=len(adfs_format.surface_specs),
            sectors_per_track=spec.sectors_per_track,
        )
    with _create_image_file(filepath, adfs_format, geom, title, boot_option) as adfs:
        yield adfs


@contextmanager
def _create_hard_disc_file(
    filepath: Path,
    *,
    adfs_format: ADFSFormat,
    capacity_bytes: int,
    cylinders: int,
    heads: int,
    sectors_per_track: int,
    title: str,
    boot_option: int,
) -> Iterator[ADFS]:
    """Create a hard disc image file with .dsc sidecar."""
    if adfs_format is not None:
        raise ValueError(
            "Cannot specify adfs_format for hard disc images; "
            "use capacity_bytes or cylinders/heads instead"
        )
    if capacity_bytes is not None and cylinders is not None:
        raise ValueError("Specify either capacity_bytes or cylinders, not both")

    if capacity_bytes is not None:
        geometry = geometry_for_capacity(
            capacity_bytes,
            heads=heads,
            sectors_per_track=sectors_per_track,
        )
    elif cylinders is not None:
        geometry = ADFSGeometry(
            cylinders=cylinders,
            heads=heads,
            sectors_per_track=sectors_per_track,
        )
    else:
        raise ValueError(
            "Hard disc images require either capacity_bytes or cylinders to be specified"
        )

    total_bytes = (
        geometry.cylinders * geometry.heads * geometry.sectors_per_track * _ADFS_BYTES_PER_SECTOR
    )
    fmt = _hard_disc_format(geometry, total_bytes)

    dat_filepath = filepath.with_suffix(".dat")
    dsc_filepath = filepath.with_suffix(".dsc")
    _write_dsc(dsc_filepath, geometry)

    with _create_image_file(dat_filepath, fmt, geometry, title, boot_option) as adfs:
        yield adfs


class ADFS:
    """Handle to an open ADFS disc image.

    The ADFS object provides disc-level metadata and serves as the factory
    for ADFSPath objects. File and directory operations are performed through
    ADFSPath.

    Example::

        with ADFS.from_file("games.adf") as adfs:
            games = adfs.root / "Games"
            for entry in games:
                print(entry.name, entry.stat().length)
            data = (games / "Elite").read_bytes()
    """

    def __init__(
        self,
        unified_disc: UnifiedDisc,
        dir_format: ADFSDirectoryFormat,
        fsm: "OldFreeSpaceMap | None",
        geometry: ADFSGeometry,
        root_address: int = _OLD_MAP_ROOT_SECTOR,
        new_map: "NewMap | None" = None,
    ):
        # _closed must be set before any attribute that property-gates
        # would touch via _require_open.
        self._closed = False
        self._d = unified_disc
        self._dir_format = dir_format
        self._fsm_ = fsm
        self._geometry = geometry
        # For old-map discs ``root_address`` is a 256-byte sector number; for
        # New Map discs it is the root's three-byte indirect disc address,
        # resolved through ``self._map`` on every read/write.
        self._root_address = root_address
        self._map = new_map
        self._afs_partition_cache = None

    @property
    def is_new_map(self) -> bool:
        """Whether this disc uses the New Map (FileCore zoned allocation)."""
        return self._map is not None

    @property
    def closed(self) -> bool:
        """Whether this handle has been closed.

        Once closed, any I/O operation raises
        :class:`oaknut.file.FilesystemClosedError`. Pure path
        manipulation on path objects bound to this handle continues
        to work.
        """
        return self._closed

    def close(self) -> None:
        """Mark this handle as closed; idempotent.

        Normally invoked automatically when the
        :meth:`from_file` / :meth:`create_file` ``with`` block exits.
        """
        if self._closed:
            return
        self._closed = True

    def _require_open(self) -> None:
        """Raise :class:`FilesystemClosedError` if this handle is closed."""
        if self._closed:
            from oaknut.file.exceptions import FilesystemClosedError

            raise FilesystemClosedError(
                "ADFS handle is closed; I/O outside the with block is not supported"
            )

    def _require_writable_map(self) -> None:
        """Guard operations that mutate a New Map disc.

        New Map writing — allocation (zone bitmap, FreeLink, zone checks) and
        even in-place directory rewrites, which must preserve the directory's
        Hugo/Nick signature and recompute the check byte — is not yet
        implemented, so New Map discs are read-only at this rung.
        """
        if self._map is not None:
            raise ADFSError("writing to New Map discs is not yet supported (read-only)")

    @property
    def _disc(self) -> UnifiedDisc:
        """The backing UnifiedDisc; raises if the handle is closed."""
        self._require_open()
        return self._d

    @property
    def _fsm(self) -> OldFreeSpaceMap:
        """The free space map; raises if the handle is closed."""
        self._require_open()
        return self._fsm_

    # --- Named constructors ---

    @staticmethod
    @contextmanager
    def from_file(filepath: Union[str, PathLike]) -> Iterator[ADFS]:
        """Open an ADFS disc image file as a context manager.

        For floppy images (``.adf``, ``.adl``), auto-detects the format
        from the image size.

        For hard disc images (``.dat``), requires a companion ``.dsc``
        sidecar file alongside it containing SCSI disc geometry.
        Either the ``.dat`` or ``.dsc`` file may be specified — the
        companion is located by swapping the extension.

        The image is opened writable when host filesystem permissions
        allow, read-only otherwise. Mutations attempted against a
        read-only-backed image raise from the mmap layer at the point
        of write.

        Args:
            filepath: Path to the disc image file.

        Yields:
            ADFS instance backed by the file.

        Raises:
            FileNotFoundError: If the file or its companion does not exist.
            ADFSError: If the image is not a valid ADFS disc.
        """
        from oaknut.discimage.open_image import open_image_mmap

        p = Path(filepath)
        ext = p.suffix.lower()

        if ext in (".dat", ".dsc"):
            dat_filepath = p.with_suffix(".dat")
            dsc_filepath = p.with_suffix(".dsc")

            if not dat_filepath.exists():
                raise FileNotFoundError(f"Hard disc data file not found: {dat_filepath}")
            if not dsc_filepath.exists():
                raise FileNotFoundError(f"Hard disc geometry file not found: {dsc_filepath}")

            geometry = _parse_dsc(dsc_filepath)
            dat_size = dat_filepath.stat().st_size
            fmt = _hard_disc_format(geometry, dat_size)

            with open_image_mmap(dat_filepath) as (mm, _writable):
                adfs = ADFS._from_buffer_with_format(memoryview(mm), fmt, geometry)
                try:
                    yield adfs
                finally:
                    adfs.close()
        else:
            # The 640K layout is ambiguous; content decides, but where it
            # cannot, the extension breaks the tie — ``.adl`` is the
            # interleaved convention, so any other suffix leans linear.
            prefer_sequential = ext != ".adl"
            with open_image_mmap(p) as (mm, _writable):
                adfs = ADFS.from_buffer(memoryview(mm), prefer_sequential=prefer_sequential)
                try:
                    yield adfs
                finally:
                    adfs.close()

    @classmethod
    def from_buffer(cls, buffer: memoryview, *, prefer_sequential: bool = False) -> ADFS:
        """Create ADFS from a buffer, auto-detecting format.

        For known floppy sizes (160KB, 320KB, 640KB), uses the
        corresponding ADFS S/M/L format.  For other sizes, treats
        the buffer as a flat hard disc image (single surface).

        At 640K the layout is ambiguous — interleaved ``.adl`` images and
        linearly-imaged ones share the same size — so the directory tree
        is walked under both to pick the one that traverses. When content
        cannot decide, *prefer_sequential* (set by the caller from the
        image's extension) breaks the tie.

        Args:
            buffer: Disc image data.
            prefer_sequential: Tiebreak toward the linear 640K layout when
                content alone cannot distinguish it from interleaved.

        Returns:
            ADFS instance.

        Raises:
            ADFSError: If the image is not a valid ADFS disc.
        """
        buf_size = len(buffer)
        geom = _FLOPPY_GEOMETRY.get(buf_size)
        if buf_size == ADFS_L.total_bytes:
            fmt = _disambiguate_640k_layout(buffer, prefer_sequential=prefer_sequential)
            return cls._from_buffer_with_format(buffer, fmt, geom)
        fmt = _ADFS_FORMATS_BY_SIZE.get(buf_size)
        if fmt is None:
            # Not a known floppy size — treat as flat hard disc image
            if buf_size % _ADFS_BYTES_PER_SECTOR != 0:
                raise ADFSError(
                    f"Buffer size ({buf_size}) is not a multiple "
                    f"of the sector size ({_ADFS_BYTES_PER_SECTOR})"
                )
            total_sectors = buf_size // _ADFS_BYTES_PER_SECTOR
            if total_sectors < _OLD_FSM_SECTORS + _OLD_DIR_SECTORS:
                raise ADFSError(
                    f"Buffer too small ({total_sectors} sectors) for ADFS "
                    f"(minimum {_OLD_FSM_SECTORS + _OLD_DIR_SECTORS} sectors)"
                )
            fmt = ADFSFormat(
                surface_specs=[
                    SurfaceSpec(
                        num_tracks=1,
                        sectors_per_track=total_sectors,
                        bytes_per_sector=_ADFS_BYTES_PER_SECTOR,
                        track_zero_offset_bytes=0,
                        track_stride_bytes=buf_size,
                    )
                ],
                total_sectors=total_sectors,
                total_bytes=buf_size,
                label="HardDisc",
            )
            # Best effort for bare buffer with no .dsc — model as single
            # cylinder so callers see a valid geometry.
            geom = ADFSGeometry(cylinders=1, heads=1, sectors_per_track=total_sectors)
        return cls._from_buffer_with_format(buffer, fmt, geom)

    @classmethod
    def _from_buffer_with_format(
        cls,
        buffer: memoryview,
        fmt: ADFSFormat,
        geometry: ADFSGeometry,
    ) -> ADFS:
        """Create ADFS from a buffer with an explicit format and geometry."""
        disc_image = DiscImage(buffer, fmt.surface_specs)
        unified = UnifiedDisc(disc_image)

        # New Map discs carry a FileCore disc record at 0x04 of zone 0 and a
        # valid zone check; try that before falling back to the Old map.
        new_map = _try_new_map(unified)
        if new_map is not None:
            return cls(
                unified,
                NewDirectoryFormat(),
                None,
                geometry,
                new_map.disc_record.root,
                new_map=new_map,
            )

        # Old map: free-space map in sectors 0-1, root located by structure.
        map_data = unified.sector_range(0, 2)
        fsm = OldFreeSpaceMap(map_data)
        dir_format, root_address = _detect_directory_layout(unified)

        return cls(unified, dir_format, fsm, geometry, root_address)

    @classmethod
    def create(
        cls,
        adfs_format: ADFSFormat,
        *,
        title: str = "",
        boot_option: int = 0,
    ) -> ADFS:
        """Create a new in-memory ADFS disc image with an empty root directory.

        Args:
            adfs_format: ADFS format (ADFS_S, ADFS_M, or ADFS_L).
            title: Disc title (default empty).
            boot_option: Boot option 0–3 (default 0).

        Returns:
            ADFS instance backed by an in-memory buffer.
        """
        buffer = memoryview(bytearray(adfs_format.total_bytes))
        disc_image = DiscImage(buffer, adfs_format.surface_specs)
        unified = UnifiedDisc(disc_image)

        if adfs_format.new_map:
            disc_record = _initialise_new_map_blank(
                unified, adfs_format.total_sectors, title, boot_option
            )
            new_map = _new_map_over(unified, disc_record)
            geom = ADFSGeometry(
                cylinders=disc_record.disc_size
                // (disc_record.heads * disc_record.sectors_per_track * disc_record.sector_size),
                heads=disc_record.heads,
                sectors_per_track=disc_record.sectors_per_track,
            )
            return cls(unified, NewDirectoryFormat(), None, geom, disc_record.root, new_map=new_map)

        _initialise_old_free_space_map(unified, adfs_format.total_sectors, boot_option)
        _initialise_old_root_directory(unified, title)

        map_data = unified.sector_range(0, 2)
        fsm = OldFreeSpaceMap(map_data)
        dir_format = OldDirectoryFormat()

        geom = _FLOPPY_GEOMETRY.get(adfs_format.total_bytes)
        if geom is None:
            # Non-standard format — derive from surface specs.
            spec = adfs_format.surface_specs[0]
            geom = ADFSGeometry(
                cylinders=spec.num_tracks,
                heads=len(adfs_format.surface_specs),
                sectors_per_track=spec.sectors_per_track,
            )

        return cls(unified, dir_format, fsm, geom)

    @staticmethod
    @contextmanager
    def create_file(
        filepath: Union[str, PathLike],
        adfs_format: ADFSFormat = None,
        *,
        capacity: "int | str | None" = None,
        cylinders: int = None,
        heads: int = 4,
        sectors_per_track: int = _SCSI_SECTORS_PER_TRACK,
        title: str = "",
        boot_option: int = 0,
    ) -> Iterator[ADFS]:
        """Create a new ADFS disc image file with an empty root directory.

        For floppy images, pass an ``ADFSFormat``::

            with ADFS.create_file("disc.adl", ADFS_L, title="MyDisc") as adfs:
                ...

        For hard disc images (``.dat``), specify either a capacity or
        explicit geometry.  A companion ``.dsc`` sidecar file is written
        automatically::

            # By capacity (str or int bytes). Geometry chosen automatically.
            with ADFS.create_file("scsi0.dat", capacity="10MB") as adfs:
                ...
            with ADFS.create_file("scsi0.dat", capacity=10 * 1024 * 1024) as adfs:
                ...

            # By explicit geometry
            with ADFS.create_file("scsi0.dat", cylinders=306, heads=4) as adfs:
                ...

        Args:
            filepath: Path for the new disc image file.
            adfs_format: Floppy format (ADFS_S, ADFS_M, or ADFS_L).
            capacity: Minimum hard disc capacity. ``int`` is bytes;
                ``str`` accepts ``"10MB"``, ``"40MiB"``, ``"1024kB"``
                etc. — see :func:`oaknut.file.capacity.parse_capacity`
                for the full suffix table.
            cylinders: Number of cylinders (hard disc).
            heads: Number of heads (default 4, hard disc only).
            sectors_per_track: Sectors per track (default 33, hard disc only).
            title: Disc title (default empty).
            boot_option: Boot option 0–3 (default 0).

        Yields:
            ADFS instance backed by the file.
        """
        from oaknut.file.capacity import parse_capacity

        if isinstance(capacity, str):
            capacity_bytes = parse_capacity(capacity)
        else:
            capacity_bytes = capacity

        p = Path(filepath)
        ext = p.suffix.lower()

        if ext in (".dat", ".dsc"):
            ctx = _create_hard_disc_file(
                p,
                adfs_format=adfs_format,
                capacity_bytes=capacity_bytes,
                cylinders=cylinders,
                heads=heads,
                sectors_per_track=sectors_per_track,
                title=title,
                boot_option=boot_option,
            )
        else:
            if adfs_format is None:
                adfs_format = _floppy_format_from_extension(ext)
            ctx = _create_floppy_file(
                p,
                adfs_format=adfs_format,
                title=title,
                boot_option=boot_option,
            )
        with ctx as adfs:
            yield adfs

    # --- Path factory ---

    @property
    def root(self) -> ADFSPath:
        """The root directory (``$``)."""
        return ADFSPath(self, "$")

    def path(self, path: str) -> ADFSPath:
        """Create an ADFSPath from a path string.

        Routes through :meth:`ADFSPath.__truediv__` so the
        Acorn-shell ``^`` parent token (and consecutive ``^^``)
        are interpreted the same way as in a slash-joined chain.

        Args:
            path: ADFS path string, e.g. ``"$.Games.Elite"``,
                ``"$"``, or ``"$.Games.^.Docs.ReadMe"``.
        """
        return self.root / path

    # --- Disc-level metadata ---

    @property
    def geometry(self) -> ADFSGeometry:
        """Authoritative disc geometry (cylinders, heads, sectors per track)."""
        return self._geometry

    @property
    def title(self) -> str:
        """Disc title (from root directory title field)."""
        return self.root.title

    @title.setter
    def title(self, value: str) -> None:
        """Set disc title by rewriting the root directory."""
        self.root.title = value

    @property
    def boot_option(self) -> "BootOption":
        """Boot option as a :class:`oaknut.file.BootOption` enum."""
        from oaknut.file import BootOption

        source = self._map if self._map is not None else self._fsm
        return BootOption(source.boot_option)

    @boot_option.setter
    def boot_option(self, value: "BootOption | int") -> None:
        """Set boot option.

        Accepts either a :class:`oaknut.file.BootOption` or a plain
        ``int`` in the range 0–3. Invalid values raise from the
        :class:`BootOption` constructor itself.
        """
        from oaknut.file import BootOption

        if self._map is not None:
            raise ADFSError("setting the boot option on New Map discs is not yet supported")
        self._fsm.set_boot_option(int(BootOption(value)))

    @property
    def free_space(self) -> int:
        """Free space in bytes."""
        source = self._map if self._map is not None else self._fsm
        return source.free_space

    @property
    def total_size(self) -> int:
        """Total disc size in bytes."""
        source = self._map if self._map is not None else self._fsm
        return source.total_size

    @property
    def disc_name(self) -> str:
        """Disc name (from the disc record on New Map, else the free space map)."""
        source = self._map if self._map is not None else self._fsm
        return source.disc_name

    @property
    def has_afs_partition(self) -> bool:
        """Whether this disc carries Level 3 File Server pointers.

        ``True`` when an AFS partition is installed in the tail of
        this old-map ADFS disc (info-sector pointers at ``&F6`` /
        ``&1F6`` of the old map are non-zero and parse cleanly).
        Cheap to call — does not construct an AFS handle.
        """
        from oaknut.afs.afs import AFS, AFSNotPresentError

        if self._map is not None:
            # AFS partitions are installed only on old-map BBC/Master discs.
            return False
        sec1, sec2 = self._fsm.afs_info_pointers
        if sec1 == 0 and sec2 == 0:
            return False
        try:
            AFS(self._disc, sec1, sec2)
        except AFSNotPresentError:
            return False
        return True

    @property
    def afs_partition(self):  # type: ignore[override]
        """Return the AFS partition handle for this disc.

        Returns an :class:`oaknut.afs.AFS` handle sharing this disc's
        :class:`~oaknut.discimage.UnifiedDisc`. Cached on first access
        so repeated reads return the same instance until that
        instance is closed.

        The returned handle does not own the underlying file — keep
        this ADFS context manager alive for as long as the AFS handle
        is in use. The caller is responsible for the AFS handle's
        lifecycle: either call :meth:`AFS.close` explicitly or use
        :meth:`open_afs_partition` which yields the same handle as a
        context manager.

        Raises:
            AFSNotPresentError: If the disc has no AFS pointers.
                Use :attr:`has_afs_partition` to test for presence
                without provoking the exception.
        """
        # Deferred import — oaknut-afs depends on oaknut-adfs, so we
        # cannot import it at module load without a cycle.
        from oaknut.afs.afs import AFS, AFSNotPresentError

        # Invalidate the cache if the previously-returned AFS handle
        # has been closed. The next caller wants a fresh handle.
        if self._afs_partition_cache is not None and self._afs_partition_cache.closed:
            self._afs_partition_cache = None
        if self._map is not None:
            raise AFSNotPresentError("New Map discs do not carry an AFS partition")
        if self._afs_partition_cache is None:
            sec1, sec2 = self._fsm.afs_info_pointers
            if sec1 == 0 and sec2 == 0:
                raise AFSNotPresentError("disc has no AFS partition (no info-sector pointers)")
            self._afs_partition_cache = AFS(self._disc, sec1, sec2)
        return self._afs_partition_cache

    @contextmanager
    def open_afs_partition(self):
        """Open the AFS partition as a context manager.

        Yields the :attr:`afs_partition` handle and calls
        :meth:`AFS.close` on clean exit or :meth:`AFS.discard` if the
        body raises — so the in-flight writes survive only when the
        ``with`` block completes successfully. This is the preferred
        idiom for AFS operations that need a lifecycle bound to a
        scope.

        Raises:
            AFSNotPresentError: If the disc has no AFS partition.
        """
        afs = self.afs_partition
        try:
            yield afs
        except BaseException:
            afs.discard()
            raise
        else:
            afs.close()

    def validate(self) -> list["ADFSValidationError"]:
        """Validate filesystem integrity.

        Returns a list of :class:`oaknut.adfs.exceptions.ADFSValidationError`
        instances — empty when the image is clean. Callers iterate the
        list to present every defect rather than aborting on the first.
        """
        errors: list[ADFSValidationError] = []
        errors.extend((self._map if self._map is not None else self._fsm).validate())
        errors.extend(self._directory_tree_errors())
        return errors

    def _directory_tree_errors(self) -> list["ADFSValidationError"]:
        """Walk the whole directory tree, collecting one error per defect.

        A disc with a valid root and free-space map can still be
        untraversable if a *subdirectory* is corrupt, so the tree is
        descended in full rather than stopping at the root. Each
        unreadable directory yields an error and is not recursed into;
        a repeated disc address is reported as a cycle.
        """
        errors: list[ADFSValidationError] = []
        try:
            root = self._read_root_directory()
        except ADFSError as exc:
            errors.append(ADFSValidationError(f"Root directory: {exc}"))
            return errors

        seen: set[int] = {self._root_address}

        def walk(directory: _ADFSDirectory, path: str) -> None:
            for entry in directory.entries:
                if not entry.is_directory:
                    continue
                child_path = f"{path}.{entry.name}"
                address = entry.indirect_disc_address
                if address in seen:
                    errors.append(
                        ADFSValidationError(
                            f"{child_path}: directory cycle to sector {address}"
                        )
                    )
                    continue
                seen.add(address)
                try:
                    subdir = self._read_directory_at(address)
                except ADFSError as exc:
                    errors.append(ADFSValidationError(f"{child_path}: {exc}"))
                    continue
                walk(subdir, child_path)

        walk(root, "$")
        return errors

    def compact(self) -> int:
        """Defragment the disc by rebuilding with sequential sector allocation.

        Reads all files and directories into memory, reinitialises the
        disc structures, and writes everything back with contiguous
        sector allocation.  The result is a single free space region
        at the end of the disc.

        Returns:
            Number of objects (files and directories, excluding root) written.
        """
        self._require_writable_map()
        # 1. Snapshot the current state
        title = self.title
        boot_option = self.boot_option
        total_sectors = self._fsm.total_sectors

        tree = self._snapshot_directory(self._read_root_directory())

        # 2. Reinitialise disc structures
        _initialise_old_free_space_map(self._disc, total_sectors, boot_option)
        _initialise_old_root_directory(self._disc, title)

        # Re-read the FSM so it reflects the fresh state
        map_data = self._disc.sector_range(0, 2)
        self._fsm_ = OldFreeSpaceMap(map_data)

        # 3. Rewrite all objects
        count = self._restore_directory(
            tree,
            _OLD_MAP_ROOT_SECTOR,
            title,
        )
        return count

    def _snapshot_directory(self, directory: _ADFSDirectory) -> list:
        """Recursively snapshot a directory tree into memory.

        Returns a list of dicts, each representing a file or subdirectory.
        Subdirectories include a recursive 'children' key.
        """
        items = []
        for entry in directory.entries:
            item = {
                "name": entry.name,
                "load_address": entry.load_address,
                "exec_address": entry.exec_address,
                "attributes": entry.attributes,
                "sequence_number": entry.sequence_number,
            }
            if entry.is_directory:
                subdir = self._read_directory_at(entry.indirect_disc_address)
                item["is_directory"] = True
                item["title"] = subdir.title
                item["children"] = self._snapshot_directory(subdir)
            else:
                item["is_directory"] = False
                item["data"] = self._read_file_data(entry)
            items.append(item)
        return items

    def _restore_directory(
        self,
        items: list,
        parent_disc_address: int,
        parent_title: str,
    ) -> int:
        """Recursively restore a directory tree to the disc.

        Returns the number of objects written (files + directories).
        """
        count = 0

        for item in items:
            if item["is_directory"]:
                # Allocate sectors for the subdirectory
                dir_sectors = self._dir_format.size_in_sectors
                start_sector = self._fsm.allocate(dir_sectors)

                # Initialise the subdirectory block
                subdir = _ADFSDirectory(
                    name=item["name"],
                    title=item["title"],
                    parent_address=parent_disc_address,
                    disc_address=start_sector,
                    entries=(),
                    sequence_number=0,
                )
                dir_data = self._disc.sector_range(start_sector, dir_sectors)
                self._dir_format.serialize(subdir, dir_data)

                # Add entry to parent
                entry = _ADFSDirectoryEntry(
                    name=item["name"],
                    load_address=item["load_address"],
                    exec_address=item["exec_address"],
                    length=self._dir_format.size_in_bytes,
                    indirect_disc_address=start_sector,
                    sequence_number=item["sequence_number"],
                    attributes=item["attributes"],
                )
                self._add_entry_to_directory(parent_disc_address, entry)

                # Recurse into children
                count += 1
                count += self._restore_directory(
                    item["children"],
                    start_sector,
                    item["title"],
                )
            else:
                # Allocate sectors for file data
                data = item["data"]
                num_sectors = (len(data) + _ADFS_BYTES_PER_SECTOR - 1) // _ADFS_BYTES_PER_SECTOR
                if num_sectors > 0:
                    start_sector = self._fsm.allocate(num_sectors)
                    sector_data = self._disc.sector_range(start_sector, num_sectors)
                    padded = data + b"\x00" * (num_sectors * _ADFS_BYTES_PER_SECTOR - len(data))
                    sector_data[:] = padded
                else:
                    start_sector = 0

                entry = _ADFSDirectoryEntry(
                    name=item["name"],
                    load_address=item["load_address"],
                    exec_address=item["exec_address"],
                    length=len(data),
                    indirect_disc_address=start_sector,
                    sequence_number=item["sequence_number"],
                    attributes=item["attributes"],
                )
                self._add_entry_to_directory(parent_disc_address, entry)
                count += 1

        return count

    def _add_entry_to_directory(
        self,
        disc_address: int,
        entry: _ADFSDirectoryEntry,
    ) -> None:
        """Add an entry to a directory in sorted order and write it back.

        ADFS directories must be sorted in ascending ASCII order
        (case-insensitive) because the ROM uses a linear scan with
        early termination for file lookup. Out-of-order entries are
        silently unreachable.
        """
        directory = self._read_directory_at(disc_address)
        entries = list(directory.entries)
        insert_key = _name_key(entry.name)
        insert_pos = len(entries)
        for i, existing in enumerate(entries):
            if _name_key(existing.name) > insert_key:
                insert_pos = i
                break
        entries.insert(insert_pos, entry)
        updated = _ADFSDirectory(
            name=directory.name,
            title=directory.title,
            parent_address=directory.parent_address,
            disc_address=directory.disc_address,
            entries=tuple(entries),
            sequence_number=directory.sequence_number,
        )
        self._write_directory_at(updated, disc_address)

    # --- Bulk operations ---

    def export_all(
        self,
        target_dirpath: Union[str, PathLike],
        *,
        preserve_metadata: bool = True,
    ) -> None:
        """Export entire filesystem preserving directory structure.

        Args:
            target_dirpath: Host directory to export into.
            preserve_metadata: If True, write .inf sidecar files.
        """
        target = Path(target_dirpath)
        target.mkdir(parents=True, exist_ok=True)

        for dirpath, dirnames, filenames in self.root.walk():
            # Create subdirectories on host
            relative = dirpath.path.replace("$", "").lstrip(".")
            if relative:
                host_dir = target / relative.replace(".", "/")
            else:
                host_dir = target
            host_dir.mkdir(parents=True, exist_ok=True)

            for filename in filenames:
                adfs_path = dirpath / filename
                host_filepath = host_dir / filename
                adfs_path.export_file(host_filepath, preserve_metadata=preserve_metadata)

    # --- Pythonic protocols ---

    def __repr__(self) -> str:
        return (
            f"ADFS(disc_name={self.disc_name!r}, "
            f"total_size={self.total_size}, "
            f"free_space={self.free_space})"
        )

    # --- Internal helpers ---

    def _read_root_directory(self) -> _ADFSDirectory:
        """Read and parse the root directory."""
        return self._read_directory_at(self._root_address)

    def _object_disc_sector(self, indirect: int) -> int:
        """Resolve an object's disc address to a 256-byte sector number.

        On old-map discs the directory entry's ``indirect_disc_address`` *is*
        the start sector. On New Map discs it is a fragment reference that the
        map resolves to a linear byte address; directories always sit on a
        sector boundary, so dividing by 256 is exact.
        """
        if self._map is None:
            return indirect
        return self._map.object_start(indirect) // _ADFS_BYTES_PER_SECTOR

    def _read_disc_bytes(self, byte_address: int, length: int) -> bytes:
        """Read *length* bytes from a linear disc byte address.

        Handles addresses that are not sector-aligned (New Map fragments are
        granular to ``bytes_per_map_bit``) by reading the covering sectors and
        slicing. Assumes a linear surface, as used by the floppy shapes.
        """
        if length == 0:
            return b""
        first_sector = byte_address // _ADFS_BYTES_PER_SECTOR
        end_sector = (byte_address + length + _ADFS_BYTES_PER_SECTOR - 1) // _ADFS_BYTES_PER_SECTOR
        data = self._disc.sector_range(first_sector, end_sector - first_sector)
        start = byte_address - first_sector * _ADFS_BYTES_PER_SECTOR
        return bytes(data[start : start + length])

    def _read_directory_at(self, disc_address: int) -> _ADFSDirectory:
        """Read and parse a directory at the given disc address.

        *disc_address* is an old-map sector number or a New Map indirect
        address; :meth:`_object_disc_sector` resolves both to a sector.
        """
        sector = self._object_disc_sector(disc_address)
        num_sectors = self._dir_format.size_in_sectors
        data = self._disc.sector_range(sector, num_sectors)
        directory = self._dir_format.parse(data, disc_address)
        _assert_entries_sorted(directory.entries)
        return directory

    def _read_file_data(self, entry: _ADFSDirectoryEntry) -> bytes:
        """Read file data for a directory entry."""
        if entry.length == 0:
            return b""
        if self._map is not None:
            # New Map: gather the object's fragments via the allocation map.
            return self._map.read_object(entry.indirect_disc_address, entry.length)
        start_sector = entry.start_sector
        num_sectors = (entry.length + _ADFS_BYTES_PER_SECTOR - 1) // _ADFS_BYTES_PER_SECTOR
        data = self._disc.sector_range(start_sector, num_sectors)
        return data[: entry.length]

    def _write_directory_at(self, directory: _ADFSDirectory, disc_address: int) -> None:
        """Serialize a directory back to its sectors on disc."""
        _assert_entries_sorted(directory.entries)
        sector = self._object_disc_sector(disc_address)
        num_sectors = self._dir_format.size_in_sectors
        data = self._disc.sector_range(sector, num_sectors)
        self._dir_format.serialize(directory, data)

    # --- Map-agnostic allocation ---
    #
    # An object's "address" is a start sector on old-map discs and a fragment
    # indirect address on New Map discs. These helpers hide that difference so
    # the file/directory write paths are shared. The value stored in a
    # directory entry's ``indirect_disc_address`` is whatever ``_allocate_object``
    # returns, and ``_free_object`` / ``_write_object_data`` take the same value.

    def _allocate_object(self, length_bytes: int) -> int:
        """Allocate space for *length_bytes*; return its entry address."""
        if self._map is not None:
            return self._map.allocate_object(length_bytes)
        if length_bytes == 0:
            return 0
        num_sectors = (length_bytes + _ADFS_BYTES_PER_SECTOR - 1) // _ADFS_BYTES_PER_SECTOR
        return self._fsm.allocate(num_sectors)

    def _free_object(self, address: int, length_bytes: int) -> None:
        """Release the space previously allocated for an object."""
        if self._map is not None:
            self._map.free_object(address)
            return
        num_sectors = (length_bytes + _ADFS_BYTES_PER_SECTOR - 1) // _ADFS_BYTES_PER_SECTOR
        if num_sectors > 0:
            self._fsm.free(address, num_sectors)

    def _write_object_data(self, address: int, data: bytes) -> None:
        """Write an object's data at its allocated address."""
        if len(data) == 0:
            return
        if self._map is not None:
            self._map.write_object_data(address, data)
            return
        num_sectors = (len(data) + _ADFS_BYTES_PER_SECTOR - 1) // _ADFS_BYTES_PER_SECTOR
        view = self._disc.sector_range(address, num_sectors)
        view[:] = data + b"\x00" * (num_sectors * _ADFS_BYTES_PER_SECTOR - len(data))

    @staticmethod
    def _with_entries(
        directory: _ADFSDirectory,
        new_entries: tuple,
        new_sequence: int,
    ) -> _ADFSDirectory:
        """Copy *directory* with new entries and sequence, preserving the rest.

        Notably preserves the Hugo/Nick signature so a New Map directory is not
        rewritten as "Hugo" when its entries change.
        """
        return _ADFSDirectory(
            name=directory.name,
            title=directory.title,
            parent_address=directory.parent_address,
            disc_address=directory.disc_address,
            entries=new_entries,
            sequence_number=new_sequence,
            signature=directory.signature,
        )

    def _write_file(
        self,
        path_parts: list[str],
        data: bytes,
        load_address: int,
        exec_address: int,
        locked: bool,
    ) -> None:
        """Write a file to the disc image.

        Handles sector allocation, data writing, and directory update.
        If a file with the same name already exists, it is overwritten
        and its old sectors are freed.
        """
        filename = path_parts[-1]
        parent_dir, parent_disc_address = self._resolve_parent(path_parts)

        existing = parent_dir.find(filename)
        if existing is not None and existing.is_directory:
            raise ADFSPathError(f"Cannot overwrite directory '{filename}' with a file")

        # Fail before allocating if a brand-new entry would overflow the directory.
        if existing is None and len(parent_dir.entries) >= self._dir_format.max_entries:
            raise ADFSDirectoryFullError(
                f"Directory full: maximum {self._dir_format.max_entries} entries"
            )

        # Free the old data, then allocate and write the new.
        if existing is not None:
            self._free_object(existing.indirect_disc_address, existing.length)
        address = self._allocate_object(len(data))
        self._write_object_data(address, data)

        new_entry = _ADFSDirectoryEntry(
            name=filename,
            load_address=load_address,
            exec_address=exec_address,
            length=len(data),
            indirect_disc_address=address,
            sequence_number=0,
            attributes=_ADFSRawAttributes(
                owner_read=True,
                owner_write=True,
                locked=locked,
                directory=False,
                owner_execute=False,
                public_read=True,
                public_write=False,
                public_execute=False,
                private=False,
            ),
        )

        if existing is not None:
            new_entries = tuple(
                new_entry if _name_key(e.name) == _name_key(filename) else e
                for e in parent_dir.entries
            )
        else:
            new_entries = _insert_sorted(parent_dir.entries, new_entry)

        new_seq = (parent_dir.sequence_number + 1) & 0xFF
        self._write_directory_at(
            self._with_entries(parent_dir, new_entries, new_seq), parent_disc_address
        )

    def _resolve_parent(
        self,
        path_parts: list[str],
    ) -> tuple[_ADFSDirectory, int]:
        """Navigate to the parent directory of a path.

        Args:
            path_parts: Path components, e.g. ["$", "Games", "Elite"].

        Returns:
            (parent_directory, parent_disc_address) tuple.
        """
        parent_parts = path_parts[:-1]
        if len(parent_parts) == 1:
            return self._read_root_directory(), self._root_address

        current_dir = self._read_root_directory()
        parent_disc_address = self._root_address
        for component in parent_parts[1:]:
            entry = current_dir.find(component)
            if entry is None:
                raise ADFSPathError(f"Directory not found: {component!r}")
            if not entry.is_directory:
                raise ADFSPathError(f"Not a directory: {component!r}")
            parent_disc_address = entry.indirect_disc_address
            current_dir = self._read_directory_at(parent_disc_address)
        return current_dir, parent_disc_address

    def _unlink_file(self, path_parts: list[str]) -> None:
        """Delete a file from the disc image."""
        filename = path_parts[-1]
        parent_dir, parent_disc_address = self._resolve_parent(path_parts)

        existing = parent_dir.find(filename)
        if existing is None:
            raise ADFSPathError(f"'{filename}' not found")
        if existing.is_directory:
            raise ADFSPathError(f"'{filename}' is a directory, use rmdir")
        if existing.attributes.locked:
            raise ADFSFileLockedError(f"'{filename}' is locked")

        self._free_object(existing.indirect_disc_address, existing.length)

        new_entries = tuple(
            e for e in parent_dir.entries if _name_key(e.name) != _name_key(filename)
        )
        new_seq = (parent_dir.sequence_number + 1) & 0xFF
        self._write_directory_at(
            self._with_entries(parent_dir, new_entries, new_seq), parent_disc_address
        )

    def _mkdir(self, path_parts: list[str]) -> None:
        """Create a new directory on the disc image."""
        dirname = path_parts[-1]
        parent_dir, parent_disc_address = self._resolve_parent(path_parts)

        # Check for name collision
        existing = parent_dir.find(dirname)
        if existing is not None:
            raise ADFSEntryExistsError(f"'{dirname}' already exists")

        # Check directory capacity
        if len(parent_dir.entries) >= self._dir_format.max_entries:
            raise ADFSDirectoryFullError(
                f"Directory full: maximum {self._dir_format.max_entries} entries"
            )

        # Allocate space for the new directory and initialise its block. The
        # child inherits the parent's Hugo/Nick signature.
        address = self._allocate_object(self._dir_format.size_in_bytes)
        new_directory = _ADFSDirectory(
            name=dirname,
            title=dirname,
            parent_address=parent_disc_address,
            disc_address=address,
            entries=(),
            sequence_number=0,
            signature=parent_dir.signature,
        )
        self._write_directory_at(new_directory, address)

        # Add directory entry to parent
        new_entry = _ADFSDirectoryEntry(
            name=dirname,
            load_address=0,
            exec_address=0,
            length=self._dir_format.size_in_bytes,
            indirect_disc_address=address,
            sequence_number=0,
            attributes=_ADFSRawAttributes(
                owner_read=True,
                owner_write=True,
                locked=False,
                directory=True,
                owner_execute=False,
                public_read=True,
                public_write=False,
                public_execute=False,
                private=False,
            ),
        )

        new_entries = _insert_sorted(parent_dir.entries, new_entry)
        new_seq = (parent_dir.sequence_number + 1) & 0xFF
        self._write_directory_at(
            self._with_entries(parent_dir, new_entries, new_seq), parent_disc_address
        )

    def _rmdir(self, path_parts: list[str]) -> None:
        """Remove an empty directory from the disc image."""
        dirname = path_parts[-1]
        parent_dir, parent_disc_address = self._resolve_parent(path_parts)

        existing = parent_dir.find(dirname)
        if existing is None:
            raise ADFSPathError(f"'{dirname}' not found")
        if not existing.is_directory:
            raise ADFSPathError(f"'{dirname}' is not a directory")
        if existing.attributes.locked:
            raise ADFSFileLockedError(f"'{dirname}' is locked")

        # Check the directory is empty
        subdir = self._read_directory_at(existing.indirect_disc_address)
        if subdir.entries:
            raise ADFSDirectoryNotEmptyError(f"'{dirname}' is not empty")

        self._free_object(existing.indirect_disc_address, self._dir_format.size_in_bytes)

        new_entries = tuple(
            e for e in parent_dir.entries if _name_key(e.name) != _name_key(dirname)
        )
        new_seq = (parent_dir.sequence_number + 1) & 0xFF
        self._write_directory_at(
            self._with_entries(parent_dir, new_entries, new_seq), parent_disc_address
        )

    def _rename(self, old_parts: list[str], new_parts: list[str]) -> None:
        """Rename or move a file or directory.

        Supports both same-directory renames and cross-directory moves.
        No data is copied — only directory entries are updated.
        """
        old_name = old_parts[-1]
        new_name = new_parts[-1]

        src_dir, src_disc_address = self._resolve_parent(old_parts)
        dst_dir, dst_disc_address = self._resolve_parent(new_parts)

        existing = src_dir.find(old_name)
        if existing is None:
            raise ADFSPathError(f"'{old_name}' not found")

        # Check target doesn't already exist
        if dst_dir.find(new_name) is not None:
            raise ADFSEntryExistsError(f"'{new_name}' already exists")

        # Build the entry with the new name
        renamed = _ADFSDirectoryEntry(
            name=new_name,
            load_address=existing.load_address,
            exec_address=existing.exec_address,
            length=existing.length,
            indirect_disc_address=existing.indirect_disc_address,
            sequence_number=existing.sequence_number,
            attributes=existing.attributes,
        )

        if src_disc_address == dst_disc_address:
            # Same directory — drop the old entry and re-insert under the
            # new name so the directory stays sorted (the new name may sort
            # to a different position than the old one).
            remaining = tuple(
                e for e in src_dir.entries if _name_key(e.name) != _name_key(old_name)
            )
            new_entries = _insert_sorted(remaining, renamed)
            new_seq = (src_dir.sequence_number + 1) & 0xFF
            self._write_directory_at(
                self._with_entries(src_dir, new_entries, new_seq), src_disc_address
            )
        else:
            # Cross-directory move: check capacity, remove from source, add to destination
            if len(dst_dir.entries) >= self._dir_format.max_entries:
                raise ADFSDirectoryFullError(
                    f"Destination directory full: maximum {self._dir_format.max_entries} entries"
                )

            # Remove from source
            src_entries = tuple(
                e for e in src_dir.entries if _name_key(e.name) != _name_key(old_name)
            )
            src_seq = (src_dir.sequence_number + 1) & 0xFF
            self._write_directory_at(
                self._with_entries(src_dir, src_entries, src_seq), src_disc_address
            )

            # Add to destination (re-read since it may have changed if
            # nested), keeping the directory sorted.
            dst_dir = self._read_directory_at(dst_disc_address)
            dst_entries = _insert_sorted(dst_dir.entries, renamed)
            dst_seq = (dst_dir.sequence_number + 1) & 0xFF
            self._write_directory_at(
                self._with_entries(dst_dir, dst_entries, dst_seq), dst_disc_address
            )

    def _set_locked(self, path_parts: list[str], locked: bool) -> None:
        """Set or clear the locked attribute on a file."""
        filename = path_parts[-1]
        parent_dir, parent_disc_address = self._resolve_parent(path_parts)

        existing = parent_dir.find(filename)
        if existing is None:
            raise ADFSPathError(f"'{filename}' not found")

        # Build entry with updated locked flag
        updated_attrs = _ADFSRawAttributes(
            owner_read=existing.attributes.owner_read,
            owner_write=existing.attributes.owner_write,
            locked=locked,
            directory=existing.attributes.directory,
            owner_execute=existing.attributes.owner_execute,
            public_read=existing.attributes.public_read,
            public_write=existing.attributes.public_write,
            public_execute=existing.attributes.public_execute,
            private=existing.attributes.private,
        )

        updated_entry = _ADFSDirectoryEntry(
            name=existing.name,
            load_address=existing.load_address,
            exec_address=existing.exec_address,
            length=existing.length,
            indirect_disc_address=existing.indirect_disc_address,
            sequence_number=existing.sequence_number,
            attributes=updated_attrs,
        )

        new_entries = tuple(
            updated_entry if _name_key(e.name) == _name_key(filename) else e
            for e in parent_dir.entries
        )
        new_seq = (parent_dir.sequence_number + 1) & 0xFF
        self._write_directory_at(
            self._with_entries(parent_dir, new_entries, new_seq), parent_disc_address
        )

    def _chmod(self, path_parts: list[str], access: int) -> None:
        """Set access attributes on a file or directory."""
        filename = path_parts[-1]
        parent_dir, parent_disc_address = self._resolve_parent(path_parts)

        existing = parent_dir.find(filename)
        if existing is None:
            raise ADFSPathError(f"'{filename}' not found")

        # Replace R, W, E, L, PR, PW from the Access flags;
        # preserve D, public_execute, and private from the existing entry
        updated_attrs = _ADFSRawAttributes(
            owner_read=bool(access & Access.R),
            owner_write=bool(access & Access.W),
            locked=bool(access & Access.L),
            directory=existing.attributes.directory,
            owner_execute=bool(access & Access.E),
            public_read=bool(access & Access.PR),
            public_write=bool(access & Access.PW),
            public_execute=existing.attributes.public_execute,
            private=existing.attributes.private,
        )

        updated_entry = _ADFSDirectoryEntry(
            name=existing.name,
            load_address=existing.load_address,
            exec_address=existing.exec_address,
            length=existing.length,
            indirect_disc_address=existing.indirect_disc_address,
            sequence_number=existing.sequence_number,
            attributes=updated_attrs,
        )

        new_entries = tuple(
            updated_entry if _name_key(e.name) == _name_key(filename) else e
            for e in parent_dir.entries
        )
        new_seq = (parent_dir.sequence_number + 1) & 0xFF
        self._write_directory_at(
            self._with_entries(parent_dir, new_entries, new_seq), parent_disc_address
        )

    def _set_load_address(self, path_parts: list[str], address: int) -> None:
        """Set load address on a file or directory."""
        filename = path_parts[-1]
        parent_dir, parent_disc_address = self._resolve_parent(path_parts)

        existing = parent_dir.find(filename)
        if existing is None:
            raise ADFSPathError(f"'{filename}' not found")

        updated_entry = _ADFSDirectoryEntry(
            name=existing.name,
            load_address=address,
            exec_address=existing.exec_address,
            length=existing.length,
            indirect_disc_address=existing.indirect_disc_address,
            sequence_number=existing.sequence_number,
            attributes=existing.attributes,
        )

        new_entries = tuple(
            updated_entry if _name_key(e.name) == _name_key(filename) else e
            for e in parent_dir.entries
        )
        new_seq = (parent_dir.sequence_number + 1) & 0xFF
        self._write_directory_at(
            self._with_entries(parent_dir, new_entries, new_seq), parent_disc_address
        )

    def _set_exec_address(self, path_parts: list[str], address: int) -> None:
        """Set exec address on a file or directory."""
        filename = path_parts[-1]
        parent_dir, parent_disc_address = self._resolve_parent(path_parts)

        existing = parent_dir.find(filename)
        if existing is None:
            raise ADFSPathError(f"'{filename}' not found")

        updated_entry = _ADFSDirectoryEntry(
            name=existing.name,
            load_address=existing.load_address,
            exec_address=address,
            length=existing.length,
            indirect_disc_address=existing.indirect_disc_address,
            sequence_number=existing.sequence_number,
            attributes=existing.attributes,
        )

        new_entries = tuple(
            updated_entry if _name_key(e.name) == _name_key(filename) else e
            for e in parent_dir.entries
        )
        new_seq = (parent_dir.sequence_number + 1) & 0xFF
        self._write_directory_at(
            self._with_entries(parent_dir, new_entries, new_seq), parent_disc_address
        )


def _assert_entries_sorted(entries: tuple[_ADFSDirectoryEntry, ...]) -> None:
    """Assert directory entries are case-insensitively sorted and unique.

    ADFS uses a linear scan with early termination for file lookup, so an
    out-of-order *or* duplicated entry is silently unreachable. Both are
    caught at write time rather than surfacing as mysterious "Not found"
    errors on real hardware. (Sorting alone permits equal — i.e.
    duplicate — names, so uniqueness is asserted separately.)
    """
    key = _name_key
    assert_no_duplicate_names([entry.name for entry in entries], where="ADFS directory", key=key)
    for i in range(1, len(entries)):
        prev = key(entries[i - 1].name)
        curr = key(entries[i].name)
        assert prev <= curr, (
            f"ADFS directory entries out of order: "
            f"{entries[i - 1].name!r} (#{i - 1}) > {entries[i].name!r} (#{i})"
        )


def _insert_sorted(
    entries: tuple[_ADFSDirectoryEntry, ...],
    new_entry: _ADFSDirectoryEntry,
) -> tuple[_ADFSDirectoryEntry, ...]:
    """Insert a directory entry in case-insensitive sorted order.

    ADFS directories must be sorted ascending by name because the
    ROM uses a linear scan with early termination for file lookup.
    Inserting out of order makes files unreachable.
    """
    key = _name_key(new_entry.name)
    items = list(entries)
    pos = len(items)
    for i, existing in enumerate(items):
        if _name_key(existing.name) > key:
            pos = i
            break
    items.insert(pos, new_entry)
    return tuple(items)


def _try_new_map(unified: UnifiedDisc) -> "NewMap | None":
    """Return a :class:`NewMap` if this disc uses the New Map, else ``None``.

    Parses the FileCore disc record at 0x04 of zone 0 and confirms it with a
    plausibility gate and the zone-0 check byte, so an Old-map disc (whose
    sectors 0-1 are a free-space map, not a disc record) is not misread. Only
    single-zone maps are accepted at this rung; a valid multi-zone record is
    surfaced as an error rather than silently mistaken for an Old map.
    """
    from oaknut.adfs.new_map import calculate_zone_check

    header = unified.sector_range(0, 1)
    disc_record = DiscRecord.parse(header)
    if not disc_record.looks_valid():
        return None

    sectors = disc_record.sector_size // _ADFS_BYTES_PER_SECTOR
    zone0 = unified.sector_range(0, sectors)
    if zone0[0x00] != calculate_zone_check(zone0, 0, disc_record.log2_sector_size):
        return None

    return _new_map_over(unified, disc_record)


def _new_map_over(unified: UnifiedDisc, disc_record: DiscRecord) -> NewMap:
    """Build a :class:`NewMap` over *unified* using *disc_record*.

    Shared by New Map detection and blank-image creation. The map view spans
    both zone-0 copies (primary + duplicate) so mutations can refresh the copy;
    the read/write closures resolve linear disc addresses to the covering
    sectors, so they work for any addressing granularity the map produces.
    """
    sectors = disc_record.sector_size // _ADFS_BYTES_PER_SECTOR
    map_view = unified.sector_range(0, 2 * sectors)

    def read_bytes(byte_address: int, length: int) -> bytes:
        first = byte_address // _ADFS_BYTES_PER_SECTOR
        count = (
            byte_address + length + _ADFS_BYTES_PER_SECTOR - 1
        ) // _ADFS_BYTES_PER_SECTOR - first
        data = unified.sector_range(first, count)
        start = byte_address - first * _ADFS_BYTES_PER_SECTOR
        return bytes(data[start : start + length])

    def write_bytes(byte_address: int, data: bytes) -> None:
        first = byte_address // _ADFS_BYTES_PER_SECTOR
        count = (
            byte_address + len(data) + _ADFS_BYTES_PER_SECTOR - 1
        ) // _ADFS_BYTES_PER_SECTOR - first
        view = unified.sector_range(first, count)
        start = byte_address - first * _ADFS_BYTES_PER_SECTOR
        view[start : start + len(data)] = data

    return NewMap(map_view, disc_record, read_bytes, write_bytes)


def _detect_directory_layout(unified: UnifiedDisc) -> tuple[ADFSDirectoryFormat, int]:
    """Detect the directory format and root sector for an old-map disc.

    Returns ``(format, root_sector)``:

      * Old directory (S/M/L) — root at sector 2 (0x200);
      * New directory (D) — root at sector 4 (0x400).

    Each candidate is confirmed by parsing it in full (signature, tail and,
    for the New directory, the ROR-13 check byte), so a "Hugo"/"Nick" byte
    pattern that is really file data cannot be mistaken for a root.

    Raises:
        ADFSError: If neither layout yields a valid root directory.
    """
    old = OldDirectoryFormat()
    try:
        old_data = unified.sector_range(_OLD_MAP_ROOT_SECTOR, old.size_in_sectors)
        old.parse(old_data, _OLD_MAP_ROOT_SECTOR)
        return old, _OLD_MAP_ROOT_SECTOR
    except ADFSDirectoryError:
        pass

    new = NewDirectoryFormat()
    try:
        new_data = unified.sector_range(_D_MAP_ROOT_SECTOR, new.size_in_sectors)
        new.parse(new_data, _D_MAP_ROOT_SECTOR)
        return new, _D_MAP_ROOT_SECTOR
    except ADFSDirectoryError:
        pass

    sig2 = bytes(unified.sector_range(_OLD_MAP_ROOT_SECTOR, 1)[1:5])
    sig4 = bytes(unified.sector_range(_D_MAP_ROOT_SECTOR, 1)[1:5])
    raise ADFSError(
        "Unrecognised ADFS directory format. Expected a valid Old directory at "
        f"0x200 (got signature {sig2!r}) or New directory at 0x400 (got {sig4!r})."
    )

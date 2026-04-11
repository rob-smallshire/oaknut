"""Build minimal, valid AFS images in-memory for integration tests.

This helper composes the already-tested layers (info sector, cylinder
bitmap, map sector, directory, passwords file) into a coherent
synthetic AFS region living inside an ADFS-L disc. It does **not**
go through the allocator or any mutating path — sector addresses are
hard-coded by the caller. The goal is to exercise the read path end
to end without depending on a captured real-world image.

The resulting image has the following layout:

- ADFS old map at sectors 0..1 (from ``ADFS.create(ADFS_L)``), with
  WFSINIT-style AFS info-sector pointers patched in at ``&F6`` / ``&1F6``.
- AFS info sectors ``sec1`` / ``sec2`` = first sectors of cylinders
  ``start_cylinder`` and ``start_cylinder + 1`` respectively.
- A per-cylinder bitmap at sector 0 of each AFS cylinder, marking
  everything allocated (the builder does not maintain a free list
  because tests don't allocate).
- A root-directory map sector + 2-sector directory body.
- One or more leaf files (map sector + data sectors).
- A ``$.Passwords`` file (map sector + one-sector passwords body).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from oaknut.adfs import ADFS, ADFS_L
from oaknut.afs import AFSAccess, AfsDate, SystemInternalName
from oaknut.afs.directory import DirectoryEntry, build_directory_bytes
from oaknut.afs.info_sector import InfoSector
from oaknut.afs.map_sector import Extent, MapSector
from oaknut.afs.passwords import (
    ENTRY_SIZE as PASSWORD_ENTRY_SIZE,
)
from oaknut.afs.passwords import (
    INUSE,
    SYSTPV,
)
from oaknut.afs.types import Geometry

_SECTOR_SIZE = 256
_SPC = 16  # ADFS-L sectors per (unified) cylinder — 160 cyls × 16 spt

# Default synthetic disc geometry: ADFS-L (160 cyls × 16 sectors) with
# the AFS region starting at cylinder 140, leaving cylinders 140..159
# (20 cylinders, 320 sectors) for AFS.
DEFAULT_START_CYLINDER = 140


@dataclass
class SyntheticFile:
    name: str
    contents: bytes
    load_address: int = 0x00008000
    exec_address: int = 0x00008023
    access: str = "LR/R"


@dataclass
class ChainSpec:
    """A file to be laid out across a chain of map blocks.

    ``block_sizes`` lists the number of **data sectors** each map
    block's extents should cover, in chain order. Each block's
    extents are one sector long (maximally fragmented). A chain of
    e.g. ``[48, 5]`` gives 48 extents in the head block plus 5 in a
    single tail block, for 53 logical sectors total. The first
    block must have exactly 48 extents for the chain pointer to be
    reachable (per the ROM's MPGSGB semantics).

    Each sector is populated with distinct bytes: sector N contains
    the bytes ``((N & 0xFF),) * 256`` so callers can reconstruct
    the expected content. ``last_sector_bytes`` is set on the final
    block only.
    """

    name: str
    block_sizes: list[int]
    last_sector_bytes: int = 0
    load_address: int = 0x00008000
    exec_address: int = 0x00008023
    access: str = "LR/R"

    @property
    def total_sectors(self) -> int:
        return sum(self.block_sizes)

    def sector_content(self, logical_index: int) -> bytes:
        return bytes(((logical_index & 0xFF),) * 256)

    def expected_bytes(self) -> bytes:
        total = self.total_sectors
        raw = b"".join(self.sector_content(i) for i in range(total))
        if self.last_sector_bytes == 0:
            return raw
        return raw[: (total - 1) * 256 + self.last_sector_bytes]


@dataclass
class SyntheticUser:
    name: str
    password: str = ""
    free_space: int = 0x40404
    system: bool = False


def _encode_user(user: SyntheticUser) -> bytes:
    raw = bytearray(PASSWORD_ENTRY_SIZE)
    name_bytes = user.name.encode("ascii")
    raw[: len(name_bytes)] = name_bytes
    if len(name_bytes) < 20:
        raw[len(name_bytes)] = 0x0D  # CR terminator
    pwd_bytes = user.password.encode("ascii")
    raw[20 : 20 + len(pwd_bytes)] = pwd_bytes
    if len(pwd_bytes) < 6:
        raw[20 + len(pwd_bytes)] = 0x0D
    raw[26:30] = user.free_space.to_bytes(4, "little")
    status = INUSE
    if user.system:
        status |= SYSTPV
    raw[30] = status
    return bytes(raw)


def _pad_to_sector(data: bytes) -> bytes:
    n = len(data)
    if n % _SECTOR_SIZE == 0:
        return data
    return data + b"\x00" * (_SECTOR_SIZE - n % _SECTOR_SIZE)


def build_synthetic_adfs_with_afs(
    *,
    start_cylinder: int = DEFAULT_START_CYLINDER,
    disc_name: str = "SynthTestDisc",
    root_files: list[SyntheticFile] | None = None,
    chain_files: list[ChainSpec] | None = None,
    root_directory_sectors: int = 2,
    users: list[SyntheticUser] | None = None,
    date: datetime.date = datetime.date(2026, 4, 11),
) -> ADFS:
    """Construct an in-memory ADFS-L disc containing a valid AFS region.

    Returns the ADFS handle; the caller can then access
    ``adfs.afs_partition`` to exercise the integration path, or reach
    in and grab ``adfs._disc`` for direct sector inspection.
    """
    if root_files is None:
        root_files = [SyntheticFile(name="Hello", contents=b"Hello, AFS!\n")]
    if chain_files is None:
        chain_files = []
    if users is None:
        users = [SyntheticUser("Syst", system=True), SyntheticUser("guest")]

    adfs = ADFS.create(ADFS_L)
    total_sectors = ADFS_L.total_sectors
    num_cylinders_afs = total_sectors // _SPC - start_cylinder

    sec1 = start_cylinder * _SPC + 1
    sec2 = sec1 + _SPC

    # ----- Allocate physical sector addresses for each AFS object -----
    # The bitmap sector of each AFS cylinder is implicit (sector 0 of
    # that cylinder). We lay out everything else linearly after the
    # second info sector, starting one cylinder past ``start_cylinder``
    # (so cylinders ``start_cylinder`` and ``start_cylinder+1`` hold
    # the two info sectors).

    data_cyl = start_cylinder + 2
    cursor = data_cyl * _SPC + 1  # skip the cylinder's bitmap sector

    def alloc(n: int) -> int:
        nonlocal cursor
        # Pad across cylinder bitmaps: never let an allocation span
        # into a cylinder's sector-0 bitmap. Simpler here: advance past
        # the bitmap if we'd hit one.
        start = cursor
        for _ in range(n):
            if cursor % _SPC == 0:
                cursor += 1  # skip bitmap sector
            cursor += 1
        return start

    root_dir_size_sectors = root_directory_sectors
    passwords_body_sectors = 1

    root_map_sin = alloc(1)
    root_data_start = alloc(root_dir_size_sectors)

    file_slots: list[tuple[SyntheticFile, int, int, int]] = []  # (file, map_sin, data_sec, n_sectors)
    for f in root_files:
        n_sectors = max(1, (len(f.contents) + _SECTOR_SIZE - 1) // _SECTOR_SIZE)
        map_sin = alloc(1)
        data_sec = alloc(n_sectors)
        file_slots.append((f, map_sin, data_sec, n_sectors))

    # Allocate SINs and data sectors for chained files. Each chain
    # block's data extents are maximally fragmented: one extent per
    # sector, so a block of size N gets N distinct single-sector
    # extents.
    chain_slots: list[
        tuple[ChainSpec, list[int], list[list[int]]]
    ] = []  # (spec, block_sins, per_block_sector_lists)
    for chain in chain_files:
        block_sins: list[int] = []
        per_block_sectors: list[list[int]] = []
        for block_size in chain.block_sizes:
            block_sins.append(alloc(1))
            per_block_sectors.append([alloc(1) for _ in range(block_size)])
        chain_slots.append((chain, block_sins, per_block_sectors))

    passwords_map_sin = alloc(1)
    passwords_data_sec = alloc(passwords_body_sectors)

    # ----- Build the root directory -----
    entries: list[DirectoryEntry] = []
    file_sin_lookup: dict[str, int] = {}
    for f, map_sin, _data_sec, _n in file_slots:
        entries.append(
            DirectoryEntry(
                name=f.name,
                load_address=f.load_address,
                exec_address=f.exec_address,
                access=AFSAccess.from_string(f.access),
                date=AfsDate(date),
                sin=SystemInternalName(map_sin),
            )
        )
        file_sin_lookup[f.name] = map_sin
    for chain, block_sins, _ in chain_slots:
        entries.append(
            DirectoryEntry(
                name=chain.name,
                load_address=chain.load_address,
                exec_address=chain.exec_address,
                access=AFSAccess.from_string(chain.access),
                date=AfsDate(date),
                sin=SystemInternalName(block_sins[0]),
            )
        )
        file_sin_lookup[chain.name] = block_sins[0]
    entries.append(
        DirectoryEntry(
            name="Passwords",
            load_address=0,
            exec_address=0,
            access=AFSAccess.from_byte(0),
            date=AfsDate(date),
            sin=SystemInternalName(passwords_map_sin),
        )
    )
    root_bytes = build_directory_bytes(
        name="$",
        master_sequence_number=0,
        entries=entries,
        size_in_bytes=root_dir_size_sectors * _SECTOR_SIZE,
    )

    # ----- Write everything to the unified disc -----
    disc = adfs._disc

    def write_sector(address: int, data: bytes) -> None:
        assert len(data) == _SECTOR_SIZE, (address, len(data))
        view = disc.sector_range(address, 1)
        view[:] = data

    def write_sectors(address: int, data: bytes) -> None:
        assert len(data) % _SECTOR_SIZE == 0
        for i in range(0, len(data), _SECTOR_SIZE):
            write_sector(address + i // _SECTOR_SIZE, data[i : i + _SECTOR_SIZE])

    # Info sector (both copies identical).
    info = InfoSector(
        disc_name=disc_name,
        cylinders=total_sectors // _SPC,
        total_sectors=total_sectors,
        sectors_per_cylinder=_SPC,
        root_sin=SystemInternalName(root_map_sin),
        date=AfsDate(date),
        start_cylinder=start_cylinder,
    )
    info_bytes = info.to_bytes()
    write_sector(sec1, info_bytes)
    write_sector(sec2, info_bytes)

    # Per-cylinder bitmaps: mark sector 0 as allocated, rest free.
    # The AFS read path only inspects them via ``free_sectors``, so a
    # correct zero-cylinder-0 bitmap is sufficient.
    for cyl_index in range(num_cylinders_afs):
        physical = start_cylinder + cyl_index
        bitmap = bytearray(_SECTOR_SIZE)
        # Sectors 1..spc-1 free → all-ones except bit 0.
        bitmap[0] = 0xFF & ~0x01
        for byte_idx in range(1, _SPC // 8):
            bitmap[byte_idx] = 0xFF
        write_sector(physical * _SPC, bytes(bitmap))

    # Root directory: map sector + data.
    root_map = MapSector(
        sin=SystemInternalName(root_map_sin),
        extents=(Extent(start=root_data_start, length=root_dir_size_sectors),),
        last_sector_bytes=0,
    )
    write_sector(root_map_sin, root_map.to_bytes())
    write_sectors(root_data_start, root_bytes)

    # Each leaf file: map sector + data sectors.
    for f, map_sin, data_sec, n_sectors in file_slots:
        last_bytes = len(f.contents) % _SECTOR_SIZE
        file_map = MapSector(
            sin=SystemInternalName(map_sin),
            extents=(Extent(start=data_sec, length=n_sectors),),
            last_sector_bytes=last_bytes,
        )
        write_sector(map_sin, file_map.to_bytes())
        write_sectors(data_sec, _pad_to_sector(f.contents).ljust(n_sectors * _SECTOR_SIZE, b"\x00"))

    # Chained map files: walk each chain forward, writing each map
    # block's extents + data sectors. The chain pointer in each
    # non-final block's slot 48 points at the next block's SIN.
    for chain, block_sins, per_block_sectors in chain_slots:
        total_sectors_so_far = 0
        for block_index, (block_sin, sector_list) in enumerate(
            zip(block_sins, per_block_sectors)
        ):
            is_last = block_index == len(block_sins) - 1
            extents = tuple(Extent(start=s, length=1) for s in sector_list)
            # Only the final block carries the meaningful BILB.
            bilb = chain.last_sector_bytes if is_last else 0
            next_sin = None if is_last else SystemInternalName(block_sins[block_index + 1])
            map_block = MapSector(
                sin=SystemInternalName(block_sin),
                extents=extents,
                last_sector_bytes=bilb,
                next_sin=next_sin,
            )
            write_sector(block_sin, map_block.to_bytes())
            for local_idx, sector_addr in enumerate(sector_list):
                logical_index = total_sectors_so_far + local_idx
                write_sector(sector_addr, chain.sector_content(logical_index))
            total_sectors_so_far += len(sector_list)

    # Passwords file: map sector + data sectors.
    passwords_body = b"".join(_encode_user(u) for u in users)
    passwords_body_padded = passwords_body.ljust(passwords_body_sectors * _SECTOR_SIZE, b"\x00")
    passwords_map = MapSector(
        sin=SystemInternalName(passwords_map_sin),
        extents=(Extent(start=passwords_data_sec, length=passwords_body_sectors),),
        last_sector_bytes=len(passwords_body) % _SECTOR_SIZE,
    )
    write_sector(passwords_map_sin, passwords_map.to_bytes())
    write_sectors(passwords_data_sec, passwords_body_padded)

    # Install AFS pointers into the ADFS old free-space map and
    # recompute its checksums so the host ADFS stays valid.
    adfs._fsm.install_afs_pointers(sec1, sec2)

    return adfs


def expected_geometry() -> Geometry:
    return Geometry(
        cylinders=ADFS_L.total_sectors // _SPC,
        sectors_per_cylinder=_SPC,
        total_sectors=ADFS_L.total_sectors,
    )

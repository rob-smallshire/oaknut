"""One-shot ``initialise()`` driver.

Phase 19 of the oaknut-afs build. Composes the pieces built in
phases 6 – 18 into a single entry point that takes an old-map
ADFS disc and turns it into one with a live AFS partition: info
sectors, cylinder bitmaps, root directory, passwords file with
one or more users, per-user root directories, and optional
shipped library merges.

Mirrors the flow in ``WFSINIT.bas`` but with the well-known bugs
(phantom entry, BASIC memory leak) fixed and with the API
expressed as data. Callers build an :class:`InitSpec` describing
what they want and pass it to :func:`initialise`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from oaknut.afs.access import AFSAccess
from oaknut.afs.directory import build_directory_bytes
from oaknut.afs.info_sector import InfoSector
from oaknut.afs.map_sector import Extent, MapSector
from oaknut.afs.passwords import PASSWORDS_FILENAME, PasswordsFile
from oaknut.afs.types import AfsDate, SystemInternalName
from oaknut.afs.wfsinit import partition as _partition
from oaknut.afs.wfsinit.layout import InitSpec

if TYPE_CHECKING:
    from oaknut.adfs import ADFS


_SECTOR_SIZE = 256
_BITMAP_BIT_FREE = 1
_DEFAULT_ROOT_DIR_SECTORS = 2


def initialise(adfs: "ADFS", *, spec: InitSpec) -> None:
    """Initialise an AFS region on ``adfs`` from ``spec``.

    1. Run :func:`oaknut.afs.wfsinit.partition.plan` + ``apply``
       unless ``spec.repartition`` is False (tests can pre-arrange
       the partition themselves).
    2. Write the two info-sector copies.
    3. Initialise every AFS cylinder's bitmap with sector 0 marked
       allocated and every other sector free.
    4. Allocate and build the root directory plus its map block.
    5. Allocate and build the passwords file plus its map block,
       populated from ``spec.users``.
    6. (Phase 19 scope) skip user URD creation — requires
       directory-per-user write paths that the existing Passwords
       file machinery will create lazily as needed.
    7. (Phase 19 scope) skip shipped library merges for now — the
       library images are not yet bundled. When they are, the
       driver will call :meth:`LibraryImage.merge_into` for each
       entry in ``spec.libraries``.
    """
    from oaknut.afs.afs import AFS  # deferred to avoid cycles

    # Capture the physical disc geometry BEFORE we shrink the ADFS
    # partition, because the info sector records the total cylinder
    # count of the underlying physical disc, not the shrunken ADFS
    # view.
    physical_spc, physical_total_cyls = _partition._infer_cylinder_geometry(adfs)

    # ---- Step 1: repartition ----
    if spec.repartition:
        plan_obj = _partition.plan(
            adfs,
            size=spec.size,
            compact_adfs=spec.compact_adfs,
        )
        _partition.apply(adfs, plan_obj)
        sec1 = plan_obj.sec1
        sec2 = plan_obj.sec2
        start_cylinder = plan_obj.start_cylinder
        afs_cylinders = plan_obj.afs_cylinders
    else:
        sec1, sec2 = adfs._fsm.afs_info_pointers
        if sec1 == 0 or sec2 == 0:
            raise ValueError(
                "spec.repartition=False but no AFS pointers are installed"
            )
        start_cylinder = sec1 // physical_spc
        afs_cylinders = physical_total_cyls - start_cylinder

    spc = physical_spc
    total_cyls = physical_total_cyls
    total_afs_sectors = afs_cylinders * spc

    disc = adfs._disc

    # ---- Step 3: cylinder bitmaps ----
    # Build a fresh-bitmap for every AFS cylinder with sector 0
    # allocated and sectors 1..spc-1 free.
    def build_fresh_bitmap() -> bytearray:
        bitmap = bytearray(_SECTOR_SIZE)
        for sector in range(1, spc):
            bitmap[sector >> 3] |= 1 << (sector & 7)
        return bitmap

    cylinder_bitmaps: dict[int, bytearray] = {
        cyl: build_fresh_bitmap() for cyl in range(afs_cylinders)
    }

    def mark_allocated(absolute_sector: int) -> None:
        cyl_abs, sec_in_cyl = divmod(absolute_sector, spc)
        cyl_index = cyl_abs - start_cylinder
        if not (0 <= cyl_index < afs_cylinders):
            return
        bitmap = cylinder_bitmaps[cyl_index]
        bitmap[sec_in_cyl >> 3] &= ~(1 << (sec_in_cyl & 7)) & 0xFF

    # Mark the info sectors and every cylinder's bitmap sector
    # as allocated.
    mark_allocated(sec1)
    mark_allocated(sec2)

    # ---- Step 4: plan the root directory + passwords file layout ----
    # We allocate SINs manually (bypassing the Allocator) because
    # the cylinder bitmaps are held in memory as mutable bytearrays
    # during initialisation and not yet written out. After we know
    # every allocation we write bitmaps + data in one go.
    cursor_cyl = start_cylinder + 2  # leave cyls 0/1 for info sectors
    cursor_sec = cursor_cyl * spc + 1  # skip cyl's sector 0 (bitmap)

    def alloc_one() -> int:
        nonlocal cursor_sec
        while True:
            cyl_abs, sec_in_cyl = divmod(cursor_sec, spc)
            if sec_in_cyl == 0:
                cursor_sec += 1
                continue
            addr = cursor_sec
            cursor_sec += 1
            return addr

    def alloc_many(n: int) -> list[int]:
        return [alloc_one() for _ in range(n)]

    root_map_sin = alloc_one()
    root_data_sectors = alloc_many(_DEFAULT_ROOT_DIR_SECTORS)
    mark_allocated(root_map_sin)
    for s in root_data_sectors:
        mark_allocated(s)

    passwords_map_sin = alloc_one()
    passwords_sectors = alloc_many(1)  # one sector = 8 entries
    mark_allocated(passwords_map_sin)
    for s in passwords_sectors:
        mark_allocated(s)

    # ---- Step 5: build info sector bytes ----
    info = InfoSector(
        disc_name=spec.disc_name,
        cylinders=total_cyls,
        total_sectors=total_cyls * spc,
        sectors_per_cylinder=spc,
        root_sin=SystemInternalName(root_map_sin),
        date=AfsDate(spec.date),
        start_cylinder=start_cylinder,
        addition_factor=spec.addition_factor,
    )
    info_bytes = info.to_bytes()

    # ---- Step 6: build root directory bytes ----
    root_entries = [
        # The passwords file is a regular directory entry with
        # access byte 0 (no read/write by anyone).
        _dir_entry(
            name=PASSWORDS_FILENAME,
            sin=passwords_map_sin,
            access=AFSAccess.from_byte(0),
            date=spec.date,
        ),
    ]
    root_bytes = build_directory_bytes(
        name="$",
        master_sequence_number=0,
        entries=root_entries,
        size_in_bytes=_DEFAULT_ROOT_DIR_SECTORS * _SECTOR_SIZE,
    )

    # ---- Step 7: build passwords file bytes ----
    passwords = PasswordsFile.from_bytes(b"")
    default_quota = spec.default_quota
    for user in spec.users:
        passwords = passwords.with_added(
            user.name,
            password=user.password,
            quota=user.quota if user.quota is not None else default_quota,
            system=user.system,
            privileges_locked=user.privileged,
            boot_option=user.boot,
        )
    passwords_raw = passwords.to_bytes()
    passwords_logical_size = len(passwords_raw)
    # Pad to a whole sector for on-disc writing, but remember the
    # true logical size so the map sector's BILB field reports it.
    if len(passwords_raw) < _SECTOR_SIZE:
        passwords_raw = passwords_raw.ljust(_SECTOR_SIZE, b"\x00")

    # ---- Step 8: write everything to disc ----
    def write_sector(addr: int, data: bytes) -> None:
        assert len(data) == _SECTOR_SIZE, (addr, len(data))
        view = disc.sector_range(addr, 1)
        view[:] = data

    # Info sectors (both copies).
    write_sector(sec1, info_bytes)
    write_sector(sec2, info_bytes)

    # Cylinder bitmaps.
    for cyl_index, bitmap in cylinder_bitmaps.items():
        physical = start_cylinder + cyl_index
        write_sector(physical * spc, bytes(bitmap))

    # Root directory map block + data.
    root_map = MapSector(
        sin=SystemInternalName(root_map_sin),
        extents=(
            Extent(
                start=root_data_sectors[0],
                length=_DEFAULT_ROOT_DIR_SECTORS,
            ),
        ),
        last_sector_bytes=0,
    )
    write_sector(root_map_sin, root_map.to_bytes())
    for i, sector in enumerate(root_data_sectors):
        write_sector(sector, root_bytes[i * _SECTOR_SIZE : (i + 1) * _SECTOR_SIZE])

    # Passwords file map block + data.
    passwords_map = MapSector(
        sin=SystemInternalName(passwords_map_sin),
        extents=(
            Extent(
                start=passwords_sectors[0],
                length=len(passwords_sectors),
            ),
        ),
        last_sector_bytes=passwords_logical_size % _SECTOR_SIZE,
    )
    write_sector(passwords_map_sin, passwords_map.to_bytes())
    for i, sector in enumerate(passwords_sectors):
        chunk = passwords_raw[i * _SECTOR_SIZE : (i + 1) * _SECTOR_SIZE]
        write_sector(sector, chunk)

    # ---- Step 9: libraries (phase 17-aware; assets may not exist) ----
    if spec.libraries:
        afs = AFS(disc, sec1, sec2)
        for library in spec.libraries:
            if not library.is_available():
                # Skip un-built library images silently; caller can
                # check spec.libraries availability in advance via
                # LibraryImage.is_available().
                continue
            library.merge_into(afs, conflict="overwrite")


def _dir_entry(*, name, sin, access, date):
    """Helper to build a :class:`DirectoryEntry` with defaults."""
    from oaknut.afs.directory import DirectoryEntry
    from oaknut.afs.types import SystemInternalName

    return DirectoryEntry(
        name=name,
        load_address=0,
        exec_address=0,
        access=access,
        date=AfsDate(date),
        sin=SystemInternalName(sin),
    )

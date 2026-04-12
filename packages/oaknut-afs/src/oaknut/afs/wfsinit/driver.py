"""One-shot ``initialise()`` driver.

Phase 19 of the oaknut-afs build. Composes the pieces built in
phases 6 – 18 into a single entry point that takes an old-map
ADFS disc and turns it into one with a live AFS partition: info
sectors, cylinder bitmaps, root directory, passwords file with
one or more users, per-user root directories, and optional
shipped library merges.

Mirrors the flow in ``WFSINIT.bas`` (see ``PROCsetup`` at
line 2060 and the analysis in ``wfsinit.md``) but with the
well-known bugs (phantom entry, BASIC memory leak) fixed and with
the API expressed as data. Callers build an :class:`InitSpec`
describing what they want and pass it to :func:`initialise`.

WFSINIT creates three built-in password entries before any
user-specified accounts:

- **Syst** — system-privileged (status byte ``&C0``)
- **Boot** — standard account (status byte ``&80``)
- **Welcome** — standard account (status byte ``&80``)

These come from ``DATA 2,Boot,Welcome`` at WFSINIT.bas line 3930
and the ``FNenter_name(pass%,0,"Syst",TRUE)`` call at line 2140.
All three receive the default quota (``&40404``). We replicate
this here so that ``initialise()`` produces disc images
structurally equivalent to the original WFSINIT.

Each user-specified account also gets a **User Root Directory**
(URD): a 2-sector empty directory allocated via ``FNablk(drsz%)``
(WFSINIT line 2270) and added to the root ``$`` with access
``&30`` (directory + locked) via ``PROCenter_dir`` (line 2290).
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

    Follows the WFSINIT.bas ``PROCsetup`` flow (lines 2060-2350):

    1. Run :func:`oaknut.afs.wfsinit.partition.plan` + ``apply``
       unless ``spec.repartition`` is False.
    2. Initialise every AFS cylinder's bitmap.
    3. Allocate the root directory (map block + 2 data sectors).
    4. Allocate a URD for each user (map block + 2 data sectors).
    5. Allocate the passwords file (map block + 1 data sector).
    6. Write info sectors (both copies).
    7. Write cylinder bitmaps.
    8. Write root directory map block + data, including entries
       for each user's URD (access ``&30``) and the Passwords
       file (access ``&00``).
    9. Write each user's empty URD.
    10. Write the passwords file with built-in accounts (Syst,
        Boot, Welcome) followed by user-specified accounts.
    11. Emplace each library named in ``spec.libraries``.
    """
    from oaknut.afs.afs import AFS  # deferred to avoid cycles

    # Capture the physical disc geometry BEFORE we shrink the ADFS
    # partition, because the info sector records the total cylinder
    # count of the underlying physical disc, not the shrunken ADFS
    # view.
    physical_spc, physical_total_cyls = _partition._cylinder_geometry(adfs)

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
            raise ValueError("spec.repartition=False but no AFS pointers are installed")
        start_cylinder = sec1 // physical_spc
        afs_cylinders = physical_total_cyls - start_cylinder

    spc = physical_spc
    total_cyls = physical_total_cyls

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

    # ---- Step 4: allocate all objects ----
    # We allocate SINs manually (bypassing the Allocator) because
    # the cylinder bitmaps are held in memory as mutable bytearrays
    # during initialisation and not yet written out. After we know
    # every allocation we write bitmaps + data in one go.
    #
    # Allocation order matches WFSINIT: root dir, then per-user
    # URDs, then passwords file.
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

    # Root directory: map block + 2 data sectors.
    root_map_sin = alloc_one()
    root_data_sectors = alloc_many(_DEFAULT_ROOT_DIR_SECTORS)
    mark_allocated(root_map_sin)
    for s in root_data_sectors:
        mark_allocated(s)

    # Per-user URDs: map block + 2 data sectors each.
    # WFSINIT allocates these at lines 2270-2280 (FNablk(drsz%),
    # PROCmake_dir) for each interactively-entered user name.
    urd_allocations: list[tuple[str, int, list[int]]] = []
    for user in spec.users:
        urd_map_sin = alloc_one()
        urd_data_sectors = alloc_many(_DEFAULT_ROOT_DIR_SECTORS)
        mark_allocated(urd_map_sin)
        for s in urd_data_sectors:
            mark_allocated(s)
        urd_allocations.append((user.name, urd_map_sin, urd_data_sectors))

    # Passwords file: map block + 1 data sector.
    # WFSINIT allocates this last, at line 3030 (FNablk(pssz%)),
    # called from FNwrite_PW via PROCsetup line 2320.
    passwords_map_sin = alloc_one()
    passwords_sectors = alloc_many(1)  # one sector ≈ 8 entries
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
    # WFSINIT adds user URD entries (PROCenter_dir at line 2290,
    # access &30 = directory + locked) then the Passwords entry
    # last (line 2320, access &00). build_directory_bytes sorts
    # entries alphabetically, matching PROCenter_dir's sorted
    # insertion.
    root_entries = [
        _dir_entry(
            name=user_name,
            sin=urd_map_sin,
            access=AFSAccess.from_byte(0x30),
            date=spec.date,
        )
        for user_name, urd_map_sin, _urd_data in urd_allocations
    ]
    root_entries.append(
        _dir_entry(
            name=PASSWORDS_FILENAME,
            sin=passwords_map_sin,
            access=AFSAccess.from_byte(0),
            date=spec.date,
        ),
    )
    root_bytes = build_directory_bytes(
        name="$",
        master_sequence_number=0,
        entries=root_entries,
        size_in_bytes=_DEFAULT_ROOT_DIR_SECTORS * _SECTOR_SIZE,
    )

    # ---- Step 7: build per-user URD bytes ----
    urd_bytes_list: list[bytes] = []
    for user_name, _urd_map_sin, _urd_data in urd_allocations:
        urd_bytes = build_directory_bytes(
            name=user_name,
            master_sequence_number=0,
            entries=[],
            size_in_bytes=_DEFAULT_ROOT_DIR_SECTORS * _SECTOR_SIZE,
        )
        urd_bytes_list.append(urd_bytes)

    # ---- Step 8: build passwords file bytes ----
    # WFSINIT creates three built-in accounts before user-specified
    # ones (lines 2130-2160):
    #   Syst  — FNenter_name(pass%, 0, "Syst", TRUE) — system privilege
    #   Boot  — from DATA at line 3930
    #   Welcome — from DATA at line 3930
    # All receive the default quota (&40404).
    passwords = PasswordsFile.from_bytes(b"")
    default_quota = spec.default_quota

    # Built-in accounts (skipping any in omit_builtins).
    omitted_upper = {n.upper() for n in spec.omit_builtins}
    if "SYST" not in omitted_upper:
        passwords = passwords.with_added("Syst", quota=default_quota, system=True)
    if "BOOT" not in omitted_upper:
        passwords = passwords.with_added("Boot", quota=default_quota)
    if "WELCOME" not in omitted_upper:
        passwords = passwords.with_added("Welcome", quota=default_quota)

    # User-specified accounts.
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

    # ---- Step 9: write everything to disc ----
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

    # Per-user URD map blocks + data.
    for (user_name, urd_map_sin, urd_data_sectors), urd_bytes in zip(
        urd_allocations, urd_bytes_list
    ):
        urd_map = MapSector(
            sin=SystemInternalName(urd_map_sin),
            extents=(
                Extent(
                    start=urd_data_sectors[0],
                    length=_DEFAULT_ROOT_DIR_SECTORS,
                ),
            ),
            last_sector_bytes=0,
        )
        write_sector(urd_map_sin, urd_map.to_bytes())
        for i, sector in enumerate(urd_data_sectors):
            write_sector(sector, urd_bytes[i * _SECTOR_SIZE : (i + 1) * _SECTOR_SIZE])

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

    # ---- Step 10: emplace libraries ----
    if spec.libraries:
        from oaknut.afs.libraries import emplace_library

        with AFS(disc, sec1, sec2) as afs:
            for library_name in spec.libraries:
                emplace_library(afs, library_name, conflict="overwrite")


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

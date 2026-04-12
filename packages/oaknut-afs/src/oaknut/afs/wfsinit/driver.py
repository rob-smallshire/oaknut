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
from oaknut.afs.allocator import Allocator
from oaknut.afs.bitmap import BitmapShadow, CylinderBitmap
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

    def write_sector(addr: int, data: bytes) -> None:
        assert len(data) == _SECTOR_SIZE, (addr, len(data))
        view = disc.sector_range(addr, 1)
        view[:] = data

    # ---- Step 3: cylinder bitmaps + allocator ----
    # Build fresh bitmaps (sector 0 allocated, rest free) and wrap
    # them in a BitmapShadow + Allocator. This gives us WFSINIT's
    # FNablk allocation policy (FNDCY best-fit by cylinder, ALBLK
    # first-fit within cylinder) so objects are distributed across
    # cylinders exactly as WFSINIT does.
    fresh_bitmaps: dict[int, CylinderBitmap] = {}
    for cyl in range(afs_cylinders):
        bm = CylinderBitmap(spc)
        # Mark sectors 1..spc-1 as free; sector 0 (bitmap) stays allocated.
        for sector in range(1, spc):
            bm.set_free(sector)
        fresh_bitmaps[cyl] = bm

    def _bitmap_reader(cylinder: int) -> bytes:
        return bytes(fresh_bitmaps[cylinder].to_bytes())

    def _bitmap_writer(cylinder: int, data: bytes) -> None:
        write_sector((start_cylinder + cylinder) * spc, data)

    shadow = BitmapShadow(
        afs_cylinders, spc,
        reader=_bitmap_reader,
        writer=_bitmap_writer,
    )

    # Pre-populate the shadow cache from our fresh bitmaps so that
    # the allocator sees the correct free counts without hitting
    # the reader (which would give a snapshot, not the live state).
    for cyl, bm in fresh_bitmaps.items():
        shadow._cache[cyl] = bm
        shadow._free_counts[cyl] = bm.free_count()
        shadow._dirty.add(cyl)

    allocator = Allocator(shadow, start_cylinder=start_cylinder, sectors_per_cylinder=spc)

    # Mark the info sectors as allocated. They sit on cylinders 0
    # and 1 at sector offset 1 (sec1 = start_cylinder*spc + 1,
    # sec2 = sec1 + spc).
    sec1_cyl = (sec1 // spc) - start_cylinder
    sec2_cyl = (sec2 // spc) - start_cylinder
    shadow.mark_range_allocated(sec1_cyl, sec1 % spc, 1)
    shadow.mark_range_allocated(sec2_cyl, sec2 % spc, 1)

    # ---- Step 4: allocate all objects via FNablk policy ----
    # WFSINIT's FNablk (lines 1650-1930) allocates the map block as
    # the first free sector on the best cylinder, then allocates the
    # data sectors contiguously from the same cylinder. Our Allocator
    # does exactly this: allocate_sector() picks the best cylinder
    # for the map block, then allocate() picks the (same) best
    # cylinder for the data sectors.
    #
    # Allocation order matches WFSINIT: root dir, then per-user
    # URDs, then passwords file.

    def _fnablk(data_sectors: int) -> tuple[int, list[Extent]]:
        """Emulate FNablk: allocate a map block + data sectors.

        WFSINIT's FNablk (lines 1650-1930) picks the best cylinder
        and allocates the map block as the first free sector, then
        allocates the data sectors contiguously from that same
        cylinder. We replicate this by allocating (1 + data_sectors)
        in a single call — the allocator's FNDCY policy keeps them
        on the same cylinder — then splitting the first sector off
        as the map block SIN.
        """
        all_extents = allocator.allocate(1 + data_sectors)
        # The first sector of the first extent is the map block.
        first = all_extents[0]
        map_sin = int(first.start)
        # Trim the map block sector from the data extents.
        if first.length == 1:
            data_extents = all_extents[1:]
        else:
            data_extents = [
                Extent(start=first.start + 1, length=first.length - 1),
                *all_extents[1:],
            ]
        return map_sin, data_extents

    # Root directory: map block + 2 data sectors.
    root_map_sin, root_extents = _fnablk(_DEFAULT_ROOT_DIR_SECTORS)

    # Per-user URDs: map block + 2 data sectors each.
    # WFSINIT allocates these at lines 2270-2280 (FNablk(drsz%),
    # PROCmake_dir) for each interactively-entered user name.
    urd_allocations: list[tuple[str, int, list[Extent]]] = []
    for user in spec.users:
        urd_map_sin, urd_extents = _fnablk(_DEFAULT_ROOT_DIR_SECTORS)
        urd_allocations.append((user.name, urd_map_sin, urd_extents))

    # Passwords file: map block + 1 data sector.
    # WFSINIT allocates this last, at line 3030 (FNablk(pssz%)),
    # called from FNwrite_PW via PROCsetup line 2320.
    passwords_map_sin, passwords_extents = _fnablk(1)

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
    def write_object(map_sin: int, extents: list[Extent], data: bytes, logical_size: int) -> None:
        """Write a map block + data sectors for one object."""
        map_block = MapSector(
            sin=SystemInternalName(map_sin),
            extents=tuple(extents),
            last_sector_bytes=logical_size % _SECTOR_SIZE,
        )
        write_sector(map_sin, map_block.to_bytes())
        offset = 0
        for ext in extents:
            for s in range(ext.length):
                chunk = data[offset : offset + _SECTOR_SIZE]
                if len(chunk) < _SECTOR_SIZE:
                    chunk = chunk.ljust(_SECTOR_SIZE, b"\x00")
                write_sector(int(ext.start) + s, chunk)
                offset += _SECTOR_SIZE

    # Info sectors (both copies).
    write_sector(sec1, info_bytes)
    write_sector(sec2, info_bytes)

    # Cylinder bitmaps (flush the shadow, which writes via _bitmap_writer).
    shadow.flush()

    # Root directory map block + data.
    write_object(root_map_sin, root_extents, root_bytes, 0)

    # Per-user URD map blocks + data.
    for (user_name, urd_map_sin, urd_extents), urd_bytes in zip(
        urd_allocations, urd_bytes_list
    ):
        write_object(urd_map_sin, urd_extents, urd_bytes, 0)

    # Passwords file map block + data.
    write_object(passwords_map_sin, passwords_extents, passwords_raw, passwords_logical_size)

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

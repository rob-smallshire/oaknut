#!/usr/bin/env python3
"""Reproduce the WFSINIT reference image using oaknut's afs-init and
compare the result sector-by-sector with the original.

The reference image at tests/data/images/l3fs/l3fs-wfsinit.dat was
created by running the original WFSINIT v1.26 under Beebium with
these answers:

    Drive number: 0
    Disc name: L3DATA
    Next drive: (blank)
    Date (dd/mm/yy): 21/10/85
    Password file (Y/N): Y
    User name 1: HOLMES
    User name 2: MORIARTY
    User name 3: (blank)
    Copy master directories (Y/N): N

This script:
1. Creates a fresh 10 MB ADFS hard disc image (in a temp file).
2. Copies the FS3v126 binary from the floppy and creates !BOOT.
3. Runs oaknut's ``initialise()`` with matching parameters.
4. Compares every sector with the reference image, annotating each
   differing sector with its structural role.
"""

from __future__ import annotations

import datetime
import struct
import sys
import tempfile
from pathlib import Path

# Ensure workspace root is on sys.path for imports.
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from oaknut.adfs import ADFS  # noqa: E402
from oaknut.afs.wfsinit import InitSpec, UserSpec, initialise  # noqa: E402
from oaknut.dfs import DFS  # noqa: E402
from oaknut.dfs.formats import ACORN_DFS_80T_SINGLE_SIDED  # noqa: E402

_SECTOR_SIZE = 256
_SPC = 4 * 33  # sectors per cylinder (4 heads × 33 SPT = 132)

# Paths
_REFERENCE_IMAGE_FILEPATH = (
    _WORKSPACE_ROOT / "tests" / "data" / "images" / "l3fs" / "l3fs-wfsinit.dat"
)
_FS3V126_FLOPPY_FILEPATH = Path.home() / "Code" / "L3V126" / "FS3v126.ssd"


def create_equivalent_image(output_filepath: Path) -> None:
    """Build a disc image equivalent to what WFSINIT produced."""

    # Step 1: Read FS3v126 from the DFS floppy.
    with DFS.from_file(
        _FS3V126_FLOPPY_FILEPATH, ACORN_DFS_80T_SINGLE_SIDED
    ) as dfs:
        fs3_path = dfs.root / "$" / "FS3v126"
        fs3_data = fs3_path.read_bytes()
        fs3_stat = fs3_path.stat()

    # Step 2: Create a 10 MB ADFS hard disc image with title "L3FS".
    # Use SI 10,000,000 bytes — "disc create --capacity 10MB" parses
    # MB as SI, giving 296 cylinders at 4 heads × 33 SPT.
    with ADFS.create_file(
        output_filepath, capacity_bytes=10_000_000, title="L3FS"
    ) as adfs:
        # Step 3: Copy FS3v126 onto it.
        adfs.path("$.FS3v126").write_bytes(
            fs3_data,
            load_address=fs3_stat.load_address,
            exec_address=fs3_stat.exec_address,
        )

        # Step 4: Create !BOOT with *RUN $.FS3v126
        # The original was: printf '*RUN $.FS3v126\r' | disc put l3fs.dat '$.!BOOT' -
        # disc put defaults load/exec to 0xFFFF when no --load/--exec given.
        adfs.path("$.!BOOT").write_bytes(
            b"*RUN $.FS3v126\r",
            load_address=0xFFFF,
            exec_address=0xFFFF,
        )

    # Step 5: Re-open and run initialise().
    # Use defaults (no compaction, existing_free) to match WFSINIT.
    with ADFS.from_file(output_filepath, mode="r+b") as adfs:
        spec = InitSpec(
            disc_name="L3DATA",
            date=datetime.date(1985, 10, 21),
            users=(
                UserSpec(name="HOLMES"),
                UserSpec(name="MORIARTY"),
            ),
        )
        initialise(adfs, spec=spec)


# ---------------------------------------------------------------------------
# Sector annotation helpers
# ---------------------------------------------------------------------------


def _decode_info_sector(data: bytes) -> dict | None:
    """Decode an AFS info sector, or return None if not AFS0 magic."""
    if data[:4] != b"AFS0":
        return None
    disc_name = data[4:20].rstrip(b" \x00").decode("ascii", errors="replace")
    cylinders = struct.unpack_from("<H", data, 20)[0]
    total_sectors = int.from_bytes(data[22:25], "little")
    spc = struct.unpack_from("<H", data, 26)[0]
    root_sin = int.from_bytes(data[31:34], "little")
    start_cyl = struct.unpack_from("<H", data, 36)[0]
    return {
        "disc_name": disc_name,
        "cylinders": cylinders,
        "total_sectors": total_sectors,
        "spc": spc,
        "root_sin": root_sin,
        "start_cylinder": start_cyl,
    }


def _decode_map_header(data: bytes) -> str | None:
    """Decode a JesMap header if present."""
    if data[:6] == b"JesMap":
        sin = int.from_bytes(data[10:13], "little")
        length = int.from_bytes(data[13:15], "little")
        return f"JesMap SIN={sin} length={length}"
    return None


def _decode_passwords_header(data: bytes) -> str | None:
    """Detect a passwords file sector (user records)."""
    # Password records are 30 bytes each; first field is a 10-byte
    # CR-padded name.  Check for printable ASCII + CR pattern.
    if len(data) < 30:
        return None
    name = data[:10]
    if name[0] == 0:
        return None
    # Look for CR terminator within first 10 bytes
    if 0x0D not in name:
        return None
    cr_pos = name.index(0x0D)
    user_name = name[:cr_pos].decode("ascii", errors="replace")
    if user_name.isprintable() and len(user_name) >= 2:
        return f"Passwords (first user: {user_name})"
    return None


def _find_afs_partitions(image_bytes: bytes) -> dict[str, dict]:
    """Scan for AFS info sectors in the image and return partition info."""
    partitions = {}
    num_sectors = len(image_bytes) // _SECTOR_SIZE
    for sector in range(num_sectors):
        offset = sector * _SECTOR_SIZE
        data = image_bytes[offset : offset + _SECTOR_SIZE]
        info = _decode_info_sector(data)
        if info is not None:
            partitions[f"info@{sector}"] = info
    return partitions


def _annotate_sector(
    sector: int,
    ref_data: bytes,
    cand_data: bytes,
    ref_afs_start: int | None,
    cand_afs_start: int | None,
) -> str:
    """Return a human-readable annotation for a sector."""
    cyl, sec_in_cyl = divmod(sector, _SPC)
    parts = [f"cyl {cyl}, sec {sec_in_cyl}"]

    # ADFS free space map and root directory
    if sector <= 2:
        labels = {
            0: "ADFS FSM sector 0",
            1: "ADFS FSM sector 1",
            2: "ADFS root directory (sector 1 of 5)",
        }
        parts.append(labels[sector])
        return " | ".join(parts)

    # Check if this is a cylinder bitmap (sector 0 of a cylinder)
    if sec_in_cyl == 0:
        tags = []
        if ref_afs_start is not None and cyl >= ref_afs_start:
            tags.append(f"ref AFS bitmap (AFS cyl {cyl - ref_afs_start})")
        if cand_afs_start is not None and cyl >= cand_afs_start:
            tags.append(f"ours AFS bitmap (AFS cyl {cyl - cand_afs_start})")
        if tags:
            parts.append(" / ".join(tags))
            return " | ".join(parts)

    # Check for AFS info sector magic
    for label, data in [("ref", ref_data), ("ours", cand_data)]:
        info = _decode_info_sector(data)
        if info:
            parts.append(
                f"{label}: AFS info sector "
                f"(root_sin={info['root_sin']}, "
                f"start_cyl={info['start_cylinder']})"
            )

    # Check for JesMap
    for label, data in [("ref", ref_data), ("ours", cand_data)]:
        jm = _decode_map_header(data)
        if jm:
            parts.append(f"{label}: {jm}")

    # Check for password records
    for label, data in [("ref", ref_data), ("ours", cand_data)]:
        pw = _decode_passwords_header(data)
        if pw:
            parts.append(f"{label}: {pw}")

    # Check for directory structure (linked list with name field)
    for label, data in [("ref", ref_data), ("ours", cand_data)]:
        # Directory sectors start with MSN byte, then entry-size byte,
        # then the title area.  A "$" padded with spaces at offset 3
        # is a strong signal.
        if data[3:13] == b"$         " or data[3:13] == b"$\x20\x20\x20\x20\x20\x20\x20\x20\x20":
            parts.append(f"{label}: AFS root directory (sector 1)")
        # User directory names
        for name in (b"HOLMES", b"MORIARTY"):
            if name in data[:13]:
                parts.append(f"{label}: AFS user directory ({name.decode()})")

    return " | ".join(parts)


def compare_images(reference_filepath: Path, candidate_filepath: Path) -> None:
    """Compare two disc images sector-by-sector with annotations."""

    ref_bytes = reference_filepath.read_bytes()
    cand_bytes = candidate_filepath.read_bytes()

    ref_sectors = len(ref_bytes) // _SECTOR_SIZE
    cand_sectors = len(cand_bytes) // _SECTOR_SIZE

    if ref_sectors != cand_sectors:
        print(f"Size mismatch: reference has {ref_sectors} sectors, candidate has {cand_sectors}")
    else:
        print(f"Both images: {ref_sectors} sectors ({ref_sectors * _SECTOR_SIZE:,} bytes)")

    # Find AFS partitions in both images.
    print("\nScanning for AFS info sectors...")
    ref_afs_start = None
    cand_afs_start = None
    num_sectors = min(ref_sectors, cand_sectors)

    for sector in range(num_sectors):
        offset = sector * _SECTOR_SIZE
        ref_info = _decode_info_sector(ref_bytes[offset : offset + _SECTOR_SIZE])
        if ref_info and ref_afs_start is None:
            ref_afs_start = ref_info["start_cylinder"]
            print(
                f"  Reference AFS: start_cylinder={ref_afs_start}, "
                f"root_sin={ref_info['root_sin']}, info sector at {sector}"
            )
        cand_info = _decode_info_sector(cand_bytes[offset : offset + _SECTOR_SIZE])
        if cand_info and cand_afs_start is None:
            cand_afs_start = cand_info["start_cylinder"]
            print(
                f"  Candidate AFS: start_cylinder={cand_afs_start}, "
                f"root_sin={cand_info['root_sin']}, info sector at {sector}"
            )

    print()

    # Bytes to ignore when comparing. ADFS 1.30 writes the System VIA
    # T1 counter low byte (&FE44) as the disc ID low byte on every
    # directory/FSM flush (write_dir_and_validate at &8FB7-&8FC3 in
    # the ADFS 1.30 disassembly). This is non-deterministic — it
    # depends on the exact microsecond the flush occurs. The checksum
    # at 0x1FF is derived from it.
    #
    # We mask these bytes out so they don't appear as differences.
    _NON_DETERMINISTIC: dict[int, set[int]] = {
        # Sector 1 (FSM part 2):
        1: {
            0xFB,  # disc ID low byte (T1 counter sample)
            0xFF,  # checksum (derived from disc ID)
        },
    }

    # Collect differences, ignoring non-deterministic bytes.
    differences = []
    for sector in range(num_sectors):
        offset = sector * _SECTOR_SIZE
        ref_sector = ref_bytes[offset : offset + _SECTOR_SIZE]
        cand_sector = cand_bytes[offset : offset + _SECTOR_SIZE]
        ignored = _NON_DETERMINISTIC.get(sector, set())
        if any(
            ref_sector[i] != cand_sector[i]
            for i in range(_SECTOR_SIZE)
            if i not in ignored
        ):
            differences.append(sector)

    if not differences:
        print(f"Images are identical ({num_sectors} sectors compared).")
        return

    print(f"{len(differences)} sector(s) differ out of {num_sectors}:")
    print()

    for sector in differences:
        offset = sector * _SECTOR_SIZE
        ref_sector = ref_bytes[offset : offset + _SECTOR_SIZE]
        cand_sector = cand_bytes[offset : offset + _SECTOR_SIZE]

        annotation = _annotate_sector(
            sector, ref_sector, cand_sector, ref_afs_start, cand_afs_start,
        )
        print(f"--- Sector {sector} (0x{offset:06X}) --- {annotation}")

        ignored = _NON_DETERMINISTIC.get(sector, set())
        diff_positions = []
        for i in range(_SECTOR_SIZE):
            if ref_sector[i] != cand_sector[i] and i not in ignored:
                diff_positions.append(i)

        if len(diff_positions) <= 32:
            for pos in diff_positions:
                ref_ch = chr(ref_sector[pos]) if 0x20 <= ref_sector[pos] < 0x7F else "."
                cand_ch = chr(cand_sector[pos]) if 0x20 <= cand_sector[pos] < 0x7F else "."
                print(
                    f"  byte 0x{pos:02X}: "
                    f"ref=0x{ref_sector[pos]:02X} ({ref_ch})  "
                    f"ours=0x{cand_sector[pos]:02X} ({cand_ch})"
                )
        else:
            print(f"  {len(diff_positions)} bytes differ")
            print(f"  ref:  {ref_sector[:64].hex(' ')}")
            print(f"  ours: {cand_sector[:64].hex(' ')}")
        print()


def main() -> None:
    if not _REFERENCE_IMAGE_FILEPATH.exists():
        print(f"Reference image not found: {_REFERENCE_IMAGE_FILEPATH}", file=sys.stderr)
        sys.exit(1)

    if not _FS3V126_FLOPPY_FILEPATH.exists():
        print(f"FS3v126 floppy not found: {_FS3V126_FLOPPY_FILEPATH}", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        candidate_filepath = Path(tmpdir) / "l3fs-wfsinit.dat"
        print("Creating equivalent image with oaknut...")
        create_equivalent_image(candidate_filepath)
        print("Comparing with reference image...")
        print()
        compare_images(_REFERENCE_IMAGE_FILEPATH, candidate_filepath)


if __name__ == "__main__":
    main()

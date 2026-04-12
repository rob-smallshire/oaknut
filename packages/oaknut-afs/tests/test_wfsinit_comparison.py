"""Byte-exact comparison of oaknut's afs-init against the original WFSINIT.

The reference image at tests/data/images/l3fs/l3fs-wfsinit.dat was
created by running the original WFSINIT v1.26 under Beebium (6502
emulation) on a 10 MB ADFS hard disc containing the Level 3 File
Server binary.  WFSINIT was given these parameters:

    Drive number: 0
    Disc name: L3DATA
    Next drive: (blank)
    Date (dd/mm/yy): 21/10/85
    Password file (Y/N): Y
    User name 1: HOLMES
    User name 2: MORIARTY
    User name 3: (blank)
    Copy master directories (Y/N): N

This test reproduces those steps using oaknut's Python API and
compares every sector.  Two categories of known difference are
accommodated with documented masks:

1. **Non-deterministic disc ID** — ADFS 1.30's ``write_dir_and_validate``
   (&8FBD in the ADFS 1.30 disassembly) samples the System VIA T1
   counter low byte (&FE44) as the disc-ID low byte on every FSM
   flush.  The value depends on the exact microsecond the flush
   occurs and is inherently unreproducible.

2. **Stray CR from BBC BASIC string indirection** — ``PROCmake_dir``
   (WFSINIT.bas line 2720) writes the directory name using ``$``
   indirection, which appends a CR (&0D) terminator.  For names of
   8+ characters, the CR falls at offset ``13 + len(name)`` in the
   directory, past the region zeroed by the free-list initialisation
   at line 2740 (which writes 4 bytes at offsets 17–20).  Shorter
   names have their CR overwritten; longer names do not.  This
   affects MORIARTY (8 chars) but not HOLMES (6) or ``$`` (1).
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

import pytest
from oaknut.adfs import ADFS
from oaknut.afs.wfsinit import InitSpec, UserSpec, initialise

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_SECTOR_SIZE = 256
_REFERENCE_IMAGE_FILEPATH = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"

# -----------------------------------------------------------------------
# Known non-deterministic or buggy bytes to mask before comparison.
#
# Each entry maps an absolute sector number to a dict of
# {byte_offset: explanation} for bytes that are expected to differ
# and should be zeroed in both images before comparison.
# -----------------------------------------------------------------------
_MASKED_BYTES: dict[int, dict[int, str]] = {
    # FSM sector 1: disc-ID low byte is the System VIA T1 counter
    # sampled on every ADFS flush (write_dir_and_validate at &8FB7
    # in the ADFS 1.30 disassembly).  The checksum at 0xFF is
    # derived from it.
    1: {
        0xFB: "disc-ID low byte (VIA T1 counter sample, non-deterministic)",
        0xFF: "FSM sector 1 checksum (derived from disc-ID)",
    },
    # MORIARTY's empty URD: PROCmake_dir's BBC BASIC $ indirection
    # writes name + 10 spaces + CR.  For "MORIARTY" (8 chars), the
    # CR lands at offset 13+8=21 (0x15), past the 4-byte zero-fill
    # at offsets 17-20 from the free-list init.  Names of <= 7 chars
    # have their CR overwritten; >= 8 chars do not.  The affected
    # byte is in the first entry slot's name field and is harmless
    # (the slot is free-listed).
    #
    # The sector number is computed at test time once we know the
    # AFS partition layout; see _moriarty_urd_sector() below.
}


def _moriarty_urd_sector(image_bytes: bytes) -> int | None:
    """Find MORIARTY's URD data sector in an image.

    Scans for a directory whose name field (offset 3-12) starts with
    "MORIARTY".  Returns the sector number, or None if not found.
    """
    num_sectors = len(image_bytes) // _SECTOR_SIZE
    for sector in range(num_sectors):
        offset = sector * _SECTOR_SIZE
        # Directory name is at bytes 3-12, space-padded.
        name = image_bytes[offset + 3 : offset + 13]
        if name == b"MORIARTY  ":
            return sector
    return None


def _apply_mask(data: bytearray, sector: int, masks: dict[int, dict[int, str]]) -> None:
    """Zero out masked bytes for a given sector."""
    if sector in masks:
        for byte_offset in masks[sector]:
            data[sector * _SECTOR_SIZE + byte_offset] = 0


class TestWFSINITComparison:
    """Compare oaknut afs-init output against the WFSINIT reference image."""

    def test_byte_exact_comparison(self, tmp_path: Path) -> None:
        ref_bytes = _REFERENCE_IMAGE_FILEPATH.read_bytes()

        # Extract the FS3v126 binary and !BOOT from the reference
        # image itself — no external dependencies needed.
        with ADFS.from_file(_REFERENCE_IMAGE_FILEPATH) as ref_adfs:
            fs3_path = ref_adfs.path("$.FS3v126")
            fs3_data = fs3_path.read_bytes()
            fs3_stat = fs3_path.stat()
            boot_path = ref_adfs.path("$.!BOOT")
            boot_data = boot_path.read_bytes()
            boot_stat = boot_path.stat()

        # Create an equivalent image from scratch.
        candidate_filepath = tmp_path / "l3fs-wfsinit.dat"

        # Step 1: Create a 10 MB ADFS hard disc (SI megabytes).
        with ADFS.create_file(
            candidate_filepath, capacity_bytes=10_000_000, title="L3FS"
        ) as adfs:
            # Step 2: Copy FS3v126 with original load/exec addresses.
            adfs.path("$.FS3v126").write_bytes(
                fs3_data,
                load_address=fs3_stat.load_address,
                exec_address=fs3_stat.exec_address,
            )
            # Step 3: Create !BOOT.
            adfs.path("$.!BOOT").write_bytes(
                boot_data,
                load_address=boot_stat.load_address,
                exec_address=boot_stat.exec_address,
            )

        # Step 4: Run initialise() with WFSINIT-matching parameters.
        with ADFS.from_file(candidate_filepath, mode="r+b") as adfs:
            initialise(
                adfs,
                spec=InitSpec(
                    disc_name="L3DATA",
                    date=datetime.date(1985, 10, 21),
                    users=(
                        UserSpec(name="HOLMES"),
                        UserSpec(name="MORIARTY"),
                    ),
                ),
            )

        cand_bytes = candidate_filepath.read_bytes()

        # Both images must be the same size.
        assert len(ref_bytes) == len(cand_bytes), (
            f"Size mismatch: reference {len(ref_bytes)}, candidate {len(cand_bytes)}"
        )

        # Build the full mask table including the dynamic MORIARTY
        # URD sector.
        masks = dict(_MASKED_BYTES)
        moriarty_sector = _moriarty_urd_sector(ref_bytes)
        assert moriarty_sector is not None, "MORIARTY URD not found in reference image"
        masks[moriarty_sector] = {
            0x15: (
                "PROCmake_dir BBC BASIC $ string CR terminator; "
                "persists for names >= 8 chars (WFSINIT.bas line 2720)"
            ),
        }

        # Apply masks to mutable copies.
        ref_masked = bytearray(ref_bytes)
        cand_masked = bytearray(cand_bytes)
        num_sectors = len(ref_bytes) // _SECTOR_SIZE
        for sector in range(num_sectors):
            _apply_mask(ref_masked, sector, masks)
            _apply_mask(cand_masked, sector, masks)

        # Compare sector-by-sector for a clear failure message.
        differing_sectors = []
        for sector in range(num_sectors):
            s = sector * _SECTOR_SIZE
            if ref_masked[s : s + _SECTOR_SIZE] != cand_masked[s : s + _SECTOR_SIZE]:
                diff_bytes = [
                    i for i in range(_SECTOR_SIZE)
                    if ref_masked[s + i] != cand_masked[s + i]
                ]
                differing_sectors.append((sector, diff_bytes))

        if differing_sectors:
            lines = [f"{len(differing_sectors)} sector(s) differ:"]
            for sector, positions in differing_sectors[:10]:
                s = sector * _SECTOR_SIZE
                lines.append(f"  Sector {sector} (0x{s:06X}): {len(positions)} byte(s)")
                for pos in positions[:8]:
                    lines.append(
                        f"    byte 0x{pos:02X}: "
                        f"ref=0x{ref_masked[s+pos]:02X} "
                        f"ours=0x{cand_masked[s+pos]:02X}"
                    )
                if len(positions) > 8:
                    lines.append(f"    ... and {len(positions) - 8} more")
            pytest.fail("\n".join(lines))

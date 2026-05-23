#!/usr/bin/env python3
"""Ad-hoc inspection tool for RetroClinic Data Centre cfbackup ``.dat`` images.

Usage:
    uv run python docs/analysis/data-centre/inspect.py <image.dat> [...]

Reports:

* Old-map total disc size and checksum status (sectors 0 and 1).
* Free-space entries.
* Boot option, disc id, disc name.
* Sanity check that ``file_size_in_bytes == first_free_sector * 256``
  (the cfbackup truncation invariant).
* Root-directory listing via ``oaknut.adfs.ADFS.from_buffer``, which
  treats the file as a flat linear stream of 256-byte ADFS sectors.
"""

from __future__ import annotations

import sys
from pathlib import Path

from oaknut.adfs import ADFS
from oaknut.adfs.free_space_map import OldFreeSpaceMap
from oaknut.discimage.sectors_view import SectorsView
from oaknut.discimage.surface import DiscImage, SurfaceSpec
from oaknut.discimage.unified_disc import UnifiedDisc


def _flat_view(buf: memoryview) -> SectorsView:
    """Wrap a flat byte buffer as a single-surface ``SectorsView``."""
    spec = SurfaceSpec(
        num_tracks=1,
        sectors_per_track=len(buf) // 256,
        bytes_per_sector=256,
        track_zero_offset_bytes=0,
        track_stride_bytes=len(buf),
    )
    image = DiscImage(buf, [spec])
    return UnifiedDisc(image).sector_range(0, len(buf) // 256)


def inspect(filepath: Path) -> None:
    print(f"=== {filepath} ({filepath.stat().st_size:,} bytes) ===")
    data = bytearray(filepath.read_bytes())

    # FSM
    fsm = OldFreeSpaceMap(_flat_view(memoryview(data)))
    file_sectors = len(data) // 256
    first_free = data[0] | (data[1] << 8) | (data[2] << 16)
    print(f"  FSM total size : {fsm.total_size:,} bytes ({fsm.total_sectors:,} sectors)")
    print(f"  FSM free space : {fsm.free_space:,} bytes")
    print(f"  Boot option    : {fsm.boot_option}")
    print(f"  Disc id        : 0x{fsm.disc_id:04X}")
    print(f"  Disc name      : {fsm.disc_name!r}")
    print(f"  Free entries   : {fsm.num_entries}")
    for i, (start, length) in enumerate(fsm.free_space_entries()):
        print(f"    [{i}] start={start // 256:>8d} sec  length={length // 256:>8d} sec")
    print(
        f"  Truncation OK  : "
        f"file_sectors ({file_sectors}) == first_free ({first_free}) "
        f"→ {file_sectors == first_free}"
    )

    # Directory walk
    adfs = ADFS.from_buffer(memoryview(data))
    print("  Root entries:")
    for entry in adfs.root.iterdir():
        stat = entry.stat()
        kind = "DIR " if stat.is_directory else "FILE"
        print(
            f"    {kind} {entry.name:<12s} "
            f"load={stat.load_address:08X} "
            f"exec={stat.exec_address:08X} "
            f"size={stat.length:>8d}"
        )
    print()


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: inspect.py <image.dat> [...]", file=sys.stderr)
        return 2
    for arg in sys.argv[1:]:
        inspect(Path(arg))
    return 0


if __name__ == "__main__":
    sys.exit(main())

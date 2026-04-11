"""Phase 7 integration tests — large objects through the AFS read path.

Covers:

- A file whose map chain spans multiple map blocks, read end to end
  through ``AFSPath.read_bytes``. This is the payoff for phase 7.
- A directory containing more than 19 entries (the default 2-sector
  capacity). Current single-block directory storage is enough to
  reach ~255 entries when fitted inside a 26-sector directory, so
  directory-growth read works automatically as soon as the underlying
  map chain does.
"""

from __future__ import annotations

from helpers.afs_image import (
    ChainSpec,
    SyntheticFile,
    build_synthetic_adfs_with_afs,
)
from oaknut.afs.directory import ENTRY_SIZE as DIR_ENTRY_SIZE
from oaknut.afs.directory import HEADER_SIZE as DIR_HEADER_SIZE
from oaknut.afs.directory import TRAILING_SEQ_SIZE as DIR_TRAIL_SIZE


def _required_directory_sectors(num_entries: int) -> int:
    """Smallest whole-sector directory body that holds ``num_entries``."""
    bytes_needed = DIR_HEADER_SIZE + num_entries * DIR_ENTRY_SIZE + DIR_TRAIL_SIZE
    return (bytes_needed + 255) // 256


class TestChainedMapFileRead:
    def test_two_block_chain_round_trip(self) -> None:
        # Head block fills all 48 data extents; tail block adds 5 more.
        # Total 53 logical sectors; last sector has a 120-byte remainder.
        chain = ChainSpec(
            name="BigFile",
            block_sizes=[48, 5],
            last_sector_bytes=120,
        )
        adfs = build_synthetic_adfs_with_afs(chain_files=[chain])
        afs = adfs.afs_partition

        data = (afs.root / "BigFile").read_bytes()
        assert data == chain.expected_bytes()
        assert len(data) == 52 * 256 + 120

    def test_three_block_chain(self) -> None:
        chain = ChainSpec(
            name="Huge",
            block_sizes=[48, 48, 3],
            last_sector_bytes=0,  # last sector fully used
        )
        adfs = build_synthetic_adfs_with_afs(chain_files=[chain])
        afs = adfs.afs_partition
        data = (afs.root / "Huge").read_bytes()
        assert len(data) == 99 * 256
        assert data == chain.expected_bytes()

    def test_chain_and_small_files_coexist(self) -> None:
        chain = ChainSpec(name="Chunky", block_sizes=[48, 2])
        adfs = build_synthetic_adfs_with_afs(
            root_files=[
                SyntheticFile(name="Small", contents=b"hi"),
            ],
            chain_files=[chain],
        )
        afs = adfs.afs_partition
        names = sorted(p.name for p in afs.root)
        assert "Small" in names
        assert "Chunky" in names
        assert (afs.root / "Small").read_bytes() == b"hi"
        assert (afs.root / "Chunky").read_bytes() == chain.expected_bytes()

    def test_chain_file_stat_reports_full_length(self) -> None:
        chain = ChainSpec(name="Stat", block_sizes=[48, 1], last_sector_bytes=7)
        adfs = build_synthetic_adfs_with_afs(chain_files=[chain])
        afs = adfs.afs_partition
        # DirectoryEntry doesn't carry length directly (that's derived
        # from the map), but we can verify read_bytes size matches.
        data = (afs.root / "Stat").read_bytes()
        assert len(data) == 48 * 256 + 7


class TestLargeDirectoryRead:
    def test_50_entry_directory(self) -> None:
        files = [
            SyntheticFile(name=f"F{i:03d}", contents=f"body{i}".encode())
            for i in range(50)
        ]
        # 50 entries + the automatic Passwords entry = 51. A 6-sector
        # directory gives capacity floor((1536 - 18) / 26) = 58.
        adfs = build_synthetic_adfs_with_afs(
            root_files=files,
            root_directory_sectors=_required_directory_sectors(60),
        )
        afs = adfs.afs_partition
        names = sorted(p.name for p in afs.root)
        for i in range(50):
            assert f"F{i:03d}" in names
        assert "Passwords" in names

    def test_large_directory_round_trip_contents(self) -> None:
        files = [
            SyntheticFile(name=f"File{i:02d}", contents=f"body-{i}".encode())
            for i in range(30)
        ]
        adfs = build_synthetic_adfs_with_afs(
            root_files=files,
            root_directory_sectors=_required_directory_sectors(40),
        )
        afs = adfs.afs_partition
        for i in range(30):
            data = (afs.root / f"File{i:02d}").read_bytes()
            assert data == f"body-{i}".encode()

"""Tests for Layer 2: Sector-level disk access."""

import pytest
from oaknut_dfs.disk_image import MemoryDiskImage
from oaknut_dfs.sector_image import (
    SectorImage,
    SSDSectorImage,
    SequentialDSDSectorImage,
    InterleavedDSDSectorImage,
    DSDSideSectorImage,
)


class TestSSDSectorImage:
    """Tests for single-sided sequential sector access."""

    def test_physical_offset_sector_0(self):
        """Sector 0 is at offset 0."""
        disk = MemoryDiskImage(size=102400)  # 400 sectors
        ssd = SSDSectorImage(disk)
        assert ssd.physical_offset(0) == 0

    def test_physical_offset_sector_1(self):
        """Sector 1 is at offset 256."""
        disk = MemoryDiskImage(size=102400)
        ssd = SSDSectorImage(disk)
        assert ssd.physical_offset(1) == 256

    def test_physical_offset_sector_10(self):
        """Sector 10 (start of track 1) is at offset 2560."""
        disk = MemoryDiskImage(size=102400)
        ssd = SSDSectorImage(disk)
        assert ssd.physical_offset(10) == 2560

    def test_physical_offset_sequential(self):
        """All sectors follow sequential offset pattern."""
        disk = MemoryDiskImage(size=102400)
        ssd = SSDSectorImage(disk)
        for sector in range(400):
            assert ssd.physical_offset(sector) == sector * 256

    def test_num_sectors_40_track(self):
        """40-track SSD has 400 sectors."""
        disk = MemoryDiskImage(size=102400)  # 40 tracks × 10 sectors × 256 bytes
        ssd = SSDSectorImage(disk)
        assert ssd.num_sectors() == 400

    def test_num_sectors_80_track(self):
        """80-track SSD has 800 sectors."""
        disk = MemoryDiskImage(size=204800)  # 80 tracks × 10 sectors × 256 bytes
        ssd = SSDSectorImage(disk)
        assert ssd.num_sectors() == 800

    def test_read_sector_0(self):
        """Read first sector."""
        data = b"A" * 256 + b"B" * 256 + b"C" * 256
        disk = MemoryDiskImage(data=data)
        ssd = SSDSectorImage(disk)
        assert ssd.read_sector(0) == b"A" * 256

    def test_read_sector_1(self):
        """Read second sector."""
        data = b"A" * 256 + b"B" * 256 + b"C" * 256
        disk = MemoryDiskImage(data=data)
        ssd = SSDSectorImage(disk)
        assert ssd.read_sector(1) == b"B" * 256

    def test_read_sector_2(self):
        """Read third sector."""
        data = b"A" * 256 + b"B" * 256 + b"C" * 256
        disk = MemoryDiskImage(data=data)
        ssd = SSDSectorImage(disk)
        assert ssd.read_sector(2) == b"C" * 256

    def test_write_sector_0(self):
        """Write to first sector."""
        disk = MemoryDiskImage(size=1024)
        ssd = SSDSectorImage(disk)
        ssd.write_sector(0, b"X" * 256)
        assert ssd.read_sector(0) == b"X" * 256
        # Verify other sectors unaffected
        assert ssd.read_sector(1) == bytes(256)

    def test_write_sector_1(self):
        """Write to second sector."""
        disk = MemoryDiskImage(size=1024)
        ssd = SSDSectorImage(disk)
        ssd.write_sector(1, b"Y" * 256)
        assert ssd.read_sector(1) == b"Y" * 256
        # Verify other sectors unaffected
        assert ssd.read_sector(0) == bytes(256)
        assert ssd.read_sector(2) == bytes(256)

    def test_read_negative_sector_raises(self):
        """Reading negative sector raises ValueError."""
        disk = MemoryDiskImage(size=102400)
        ssd = SSDSectorImage(disk)
        with pytest.raises(ValueError, match="cannot be negative"):
            ssd.read_sector(-1)

    def test_read_beyond_disk_raises(self):
        """Reading beyond disk size raises ValueError."""
        disk = MemoryDiskImage(size=102400)  # 400 sectors
        ssd = SSDSectorImage(disk)
        with pytest.raises(ValueError, match="exceeds disk size"):
            ssd.read_sector(400)

    def test_write_negative_sector_raises(self):
        """Writing negative sector raises ValueError."""
        disk = MemoryDiskImage(size=102400)
        ssd = SSDSectorImage(disk)
        with pytest.raises(ValueError, match="cannot be negative"):
            ssd.write_sector(-1, b"X" * 256)

    def test_write_beyond_disk_raises(self):
        """Writing beyond disk size raises ValueError."""
        disk = MemoryDiskImage(size=102400)  # 400 sectors
        ssd = SSDSectorImage(disk)
        with pytest.raises(ValueError, match="exceeds disk size"):
            ssd.write_sector(400, b"X" * 256)

    def test_write_wrong_size_raises(self):
        """Writing wrong size data raises ValueError."""
        disk = MemoryDiskImage(size=102400)
        ssd = SSDSectorImage(disk)
        with pytest.raises(ValueError, match="must be exactly 256 bytes"):
            ssd.write_sector(0, b"Too short")

    def test_read_sectors_single(self):
        """Read single sector using read_sectors."""
        data = b"A" * 256 + b"B" * 256
        disk = MemoryDiskImage(data=data)
        ssd = SSDSectorImage(disk)
        assert ssd.read_sectors(0, 1) == b"A" * 256

    def test_read_sectors_multiple(self):
        """Read multiple consecutive sectors."""
        data = b"A" * 256 + b"B" * 256 + b"C" * 256
        disk = MemoryDiskImage(data=data)
        ssd = SSDSectorImage(disk)
        assert ssd.read_sectors(0, 3) == data

    def test_read_sectors_middle(self):
        """Read sectors from middle of disk."""
        data = b"A" * 256 + b"B" * 256 + b"C" * 256 + b"D" * 256
        disk = MemoryDiskImage(data=data)
        ssd = SSDSectorImage(disk)
        assert ssd.read_sectors(1, 2) == b"B" * 256 + b"C" * 256

    def test_read_sectors_zero_count(self):
        """Reading zero sectors returns empty bytes."""
        disk = MemoryDiskImage(size=1024)
        ssd = SSDSectorImage(disk)
        assert ssd.read_sectors(0, 0) == b""

    def test_read_sectors_negative_count_raises(self):
        """Reading negative count raises ValueError."""
        disk = MemoryDiskImage(size=1024)
        ssd = SSDSectorImage(disk)
        with pytest.raises(ValueError, match="cannot be negative"):
            ssd.read_sectors(0, -1)

    def test_write_sectors_single(self):
        """Write single sector using write_sectors."""
        disk = MemoryDiskImage(size=1024)
        ssd = SSDSectorImage(disk)
        ssd.write_sectors(0, b"X" * 256)
        assert ssd.read_sector(0) == b"X" * 256

    def test_write_sectors_multiple(self):
        """Write multiple consecutive sectors."""
        disk = MemoryDiskImage(size=1024)
        ssd = SSDSectorImage(disk)
        data = b"A" * 256 + b"B" * 256 + b"C" * 256
        ssd.write_sectors(0, data)
        assert ssd.read_sectors(0, 3) == data

    def test_write_sectors_wrong_size_raises(self):
        """Writing non-multiple of 256 raises ValueError."""
        disk = MemoryDiskImage(size=1024)
        ssd = SSDSectorImage(disk)
        with pytest.raises(ValueError, match="must be multiple of 256"):
            ssd.write_sectors(0, b"X" * 100)


class TestSequentialDSDSectorImage:
    """Tests for sequential double-sided disk access."""

    def test_physical_offset_is_sequential(self):
        """Sequential DSD uses same offset calculation as SSD."""
        disk = MemoryDiskImage(size=204800)  # 800 sectors
        dsd = SequentialDSDSectorImage(disk)
        for sector in range(800):
            assert dsd.physical_offset(sector) == sector * 256

    def test_num_sectors_40_track(self):
        """40-track DSD has 800 sectors (2 sides × 40 tracks × 10 sectors)."""
        disk = MemoryDiskImage(size=204800)
        dsd = SequentialDSDSectorImage(disk)
        assert dsd.num_sectors() == 800

    def test_num_sectors_80_track(self):
        """80-track DSD has 1600 sectors (2 sides × 80 tracks × 10 sectors)."""
        disk = MemoryDiskImage(size=409600)
        dsd = SequentialDSDSectorImage(disk)
        assert dsd.num_sectors() == 1600

    def test_read_write_sectors(self):
        """Read and write operations work correctly."""
        disk = MemoryDiskImage(size=204800)
        dsd = SequentialDSDSectorImage(disk)

        # Write to various sectors
        dsd.write_sector(0, b"A" * 256)
        dsd.write_sector(100, b"B" * 256)
        dsd.write_sector(500, b"C" * 256)

        # Verify reads
        assert dsd.read_sector(0) == b"A" * 256
        assert dsd.read_sector(100) == b"B" * 256
        assert dsd.read_sector(500) == b"C" * 256


class TestInterleavedDSDSectorImage:
    """Tests for interleaved double-sided disk access."""

    def test_physical_offset_sector_0(self):
        """Sector 0 (side 0, track 0) is at offset 0."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)
        assert dsd.physical_offset(0) == 0

    def test_physical_offset_sector_9(self):
        """Sector 9 (last sector of side 0, track 0) is at offset 2304."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)
        assert dsd.physical_offset(9) == 9 * 256  # 2304

    def test_physical_offset_sector_10(self):
        """Sector 10 (side 1, track 0, first sector) is at offset 2560."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)
        # Side 1 track 0 starts after side 0 track 0
        assert dsd.physical_offset(10) == 2560

    def test_physical_offset_sector_19(self):
        """Sector 19 (last sector of side 1, track 0) is at offset 4864."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)
        assert dsd.physical_offset(19) == 2560 + 9 * 256  # 4864

    def test_physical_offset_sector_20(self):
        """Sector 20 (side 0, track 1, first sector) is at offset 5120."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)
        # Side 0 track 1 starts after both sides of track 0
        assert dsd.physical_offset(20) == 5120

    def test_physical_offset_sector_30(self):
        """Sector 30 (side 1, track 1, first sector) is at offset 7680."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)
        # Track 1, side 1
        assert dsd.physical_offset(30) == 7680

    def test_physical_offset_pattern(self):
        """Verify interleaving pattern for first few tracks."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)

        # Track 0, Side 0: sectors 0-9
        for i in range(10):
            assert dsd.physical_offset(i) == i * 256

        # Track 0, Side 1: sectors 10-19
        for i in range(10):
            assert dsd.physical_offset(10 + i) == 2560 + i * 256

        # Track 1, Side 0: sectors 20-29
        for i in range(10):
            assert dsd.physical_offset(20 + i) == 5120 + i * 256

        # Track 1, Side 1: sectors 30-39
        for i in range(10):
            assert dsd.physical_offset(30 + i) == 7680 + i * 256

    def test_num_sectors_40_track(self):
        """40-track interleaved DSD has 800 sectors."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        assert dsd.num_sectors() == 800

    def test_num_sectors_80_track(self):
        """80-track interleaved DSD has 1600 sectors."""
        disk = MemoryDiskImage(size=409600)
        dsd = InterleavedDSDSectorImage(disk, tracks_per_side=80)
        assert dsd.num_sectors() == 1600

    def test_read_sector_side_0_track_0(self):
        """Read from side 0, track 0."""
        # Create disk with known pattern
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)

        # Write directly to physical offset 0 (sector 0)
        disk.write_bytes(0, b"SIDE0TRK0SEC0" + b"\x00" * 243)

        # Read via sector access
        assert dsd.read_sector(0).startswith(b"SIDE0TRK0SEC0")

    def test_read_sector_side_1_track_0(self):
        """Read from side 1, track 0."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)

        # Write directly to physical offset 2560 (sector 10)
        disk.write_bytes(2560, b"SIDE1TRK0SEC0" + b"\x00" * 243)

        # Read via sector access
        assert dsd.read_sector(10).startswith(b"SIDE1TRK0SEC0")

    def test_write_read_round_trip(self):
        """Write and read back sectors."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)

        # Write to various sectors across sides
        dsd.write_sector(0, b"A" * 256)  # Side 0, track 0
        dsd.write_sector(10, b"B" * 256)  # Side 1, track 0
        dsd.write_sector(20, b"C" * 256)  # Side 0, track 1
        dsd.write_sector(30, b"D" * 256)  # Side 1, track 1

        # Verify reads
        assert dsd.read_sector(0) == b"A" * 256
        assert dsd.read_sector(10) == b"B" * 256
        assert dsd.read_sector(20) == b"C" * 256
        assert dsd.read_sector(30) == b"D" * 256

    def test_interleaving_maintains_separation(self):
        """Writing to one side doesn't affect the other."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)

        # Fill side 0 track 0 with As
        for i in range(10):
            dsd.write_sector(i, b"A" * 256)

        # Fill side 1 track 0 with Bs
        for i in range(10, 20):
            dsd.write_sector(i, b"B" * 256)

        # Verify they remained separate
        for i in range(10):
            assert dsd.read_sector(i) == b"A" * 256
        for i in range(10, 20):
            assert dsd.read_sector(i) == b"B" * 256

    def test_read_sectors_across_tracks(self):
        """Read multiple sectors spanning track boundary."""
        disk = MemoryDiskImage(size=204800)
        dsd = InterleavedDSDSectorImage(disk)

        # Write pattern across track boundary
        for i in range(8, 12):  # Crosses from track 0 to track 0 side 1
            dsd.write_sector(i, bytes([i]) * 256)

        # Read across boundary
        data = dsd.read_sectors(8, 4)
        assert len(data) == 1024
        assert data[0:256] == bytes([8]) * 256
        assert data[256:512] == bytes([9]) * 256
        assert data[512:768] == bytes([10]) * 256
        assert data[768:1024] == bytes([11]) * 256


class TestDSDSideSectorImage:
    """Tests for DSD side sector access (separate catalog per side)."""

    def test_constructor_validates_side(self):
        """Constructor rejects invalid side values."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)

        # Valid sides
        DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)
        DSDSideSectorImage(interleaved, side=1, tracks_per_side=40)

        # Invalid sides
        with pytest.raises(ValueError, match="Invalid side: 2"):
            DSDSideSectorImage(interleaved, side=2, tracks_per_side=40)

        with pytest.raises(ValueError, match="Invalid side: -1"):
            DSDSideSectorImage(interleaved, side=-1, tracks_per_side=40)

    def test_side0_physical_offset_sector_0(self):
        """Side 0, sector 0 maps to physical sector 0."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)

        # Side 0, sector 0 -> physical sector 0 -> offset 0
        assert side0.physical_offset(0) == 0

    def test_side0_physical_offset_sector_9(self):
        """Side 0, sector 9 (end of track 0) maps correctly."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)

        # Side 0, sector 9 -> physical sector 9 -> offset 2304
        assert side0.physical_offset(9) == 2304

    def test_side0_physical_offset_sector_10(self):
        """Side 0, sector 10 (track 1) maps correctly."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)

        # Side 0, sector 10 -> physical sector 20 (after track 0 both sides)
        # Physical offset: 20 * 256 = 5120
        assert side0.physical_offset(10) == 5120

    def test_side1_physical_offset_sector_0(self):
        """Side 1, sector 0 maps to physical sector 10."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side1 = DSDSideSectorImage(interleaved, side=1, tracks_per_side=40)

        # Side 1, sector 0 -> physical sector 10 (side 1 of track 0)
        # Physical offset: 10 * 256 = 2560
        assert side1.physical_offset(0) == 2560

    def test_side1_physical_offset_sector_9(self):
        """Side 1, sector 9 (end of track 0) maps correctly."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side1 = DSDSideSectorImage(interleaved, side=1, tracks_per_side=40)

        # Side 1, sector 9 -> physical sector 19
        # Physical offset: 19 * 256 = 4864
        assert side1.physical_offset(9) == 4864

    def test_side1_physical_offset_sector_10(self):
        """Side 1, sector 10 (track 1) maps correctly."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side1 = DSDSideSectorImage(interleaved, side=1, tracks_per_side=40)

        # Side 1, sector 10 -> physical sector 30 (side 1 of track 1)
        # Physical offset: 30 * 256 = 7680
        assert side1.physical_offset(10) == 7680

    def test_side0_sector_range_validation(self):
        """Side 0 rejects sectors outside 0-399 range (40T)."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)

        # Valid: 0-399
        side0.physical_offset(0)
        side0.physical_offset(399)

        # Invalid: 400 and above
        with pytest.raises(ValueError, match="Invalid sector: 400"):
            side0.physical_offset(400)

        with pytest.raises(ValueError, match="Invalid sector: -1"):
            side0.physical_offset(-1)

    def test_side1_sector_range_validation(self):
        """Side 1 rejects sectors outside 0-399 range (40T)."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side1 = DSDSideSectorImage(interleaved, side=1, tracks_per_side=40)

        # Valid: 0-399
        side1.physical_offset(0)
        side1.physical_offset(399)

        # Invalid: 400 and above
        with pytest.raises(ValueError, match="Invalid sector: 400"):
            side1.physical_offset(400)

    def test_80T_side0_sector_range(self):
        """80T disk: side 0 accepts 0-799."""
        disk = MemoryDiskImage(size=409600)  # 80T DSD
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=80)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=80)

        # Valid: 0-799
        side0.physical_offset(0)
        side0.physical_offset(799)

        # Invalid: 800 and above
        with pytest.raises(ValueError, match="Invalid sector: 800"):
            side0.physical_offset(800)

    def test_read_sector_side0(self):
        """Can read sectors from side 0."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)

        # Write directly to physical sector 0 (side 0, sector 0)
        test_data = b"SIDE0-SECTOR0" + b"\x00" * (256 - 13)
        interleaved.write_sector(0, test_data)

        # Read via side0
        data = side0.read_sector(0)
        assert data == test_data

    def test_read_sector_side1(self):
        """Can read sectors from side 1."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side1 = DSDSideSectorImage(interleaved, side=1, tracks_per_side=40)

        # Write directly to physical sector 10 (side 1, sector 0)
        test_data = b"SIDE1-SECTOR0" + b"\x00" * (256 - 13)
        interleaved.write_sector(10, test_data)

        # Read via side1
        data = side1.read_sector(0)
        assert data == test_data

    def test_write_sector_side0(self):
        """Can write sectors to side 0."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)

        # Write via side0
        test_data = b"WRITE-TO-SIDE0" + b"\x00" * (256 - 14)
        side0.write_sector(5, test_data)

        # Read back directly from physical sector 5
        data = interleaved.read_sector(5)
        assert data == test_data

    def test_write_sector_side1(self):
        """Can write sectors to side 1."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side1 = DSDSideSectorImage(interleaved, side=1, tracks_per_side=40)

        # Write via side1 sector 5
        test_data = b"WRITE-TO-SIDE1" + b"\x00" * (256 - 14)
        side1.write_sector(5, test_data)

        # Read back directly from physical sector 15 (side1, track 0, sector 5)
        data = interleaved.read_sector(15)
        assert data == test_data

    def test_sides_are_independent(self):
        """Writing to one side doesn't affect the other."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)
        side1 = DSDSideSectorImage(interleaved, side=1, tracks_per_side=40)

        # Write different data to sector 0 on each side
        data0 = b"SIDE0" + b"\x00" * 251
        data1 = b"SIDE1" + b"\x00" * 251

        side0.write_sector(0, data0)
        side1.write_sector(0, data1)

        # Read back - each side should have its own data
        assert side0.read_sector(0) == data0
        assert side1.read_sector(0) == data1

    def test_size_40T(self):
        """40T disk: each side is 102400 bytes (400 sectors)."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)
        side1 = DSDSideSectorImage(interleaved, side=1, tracks_per_side=40)

        # Each side: 40 tracks * 10 sectors * 256 bytes = 102400
        assert side0.size() == 102400
        assert side1.size() == 102400

    def test_size_80T(self):
        """80T disk: each side is 204800 bytes (800 sectors)."""
        disk = MemoryDiskImage(size=409600)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=80)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=80)
        side1 = DSDSideSectorImage(interleaved, side=1, tracks_per_side=80)

        # Each side: 80 tracks * 10 sectors * 256 bytes = 204800
        assert side0.size() == 204800
        assert side1.size() == 204800

    def test_read_sector_validates_range(self):
        """read_sector() validates sector number."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)

        with pytest.raises(ValueError, match="Invalid sector"):
            side0.read_sector(400)

    def test_write_sector_validates_range(self):
        """write_sector() validates sector number."""
        disk = MemoryDiskImage(size=204800)
        interleaved = InterleavedDSDSectorImage(disk, tracks_per_side=40)
        side0 = DSDSideSectorImage(interleaved, side=0, tracks_per_side=40)

        test_data = b"\x00" * 256
        with pytest.raises(ValueError, match="Invalid sector"):
            side0.write_sector(400, test_data)


class TestSectorImageInterface:
    """Tests verifying all implementations conform to SectorImage interface."""

    @pytest.fixture(params=["ssd", "sequential_dsd", "interleaved_dsd"])
    def sector_image(self, request):
        """Parameterized fixture providing all implementations."""
        disk = MemoryDiskImage(size=204800)  # Large enough for all types
        if request.param == "ssd":
            return SSDSectorImage(disk)
        elif request.param == "sequential_dsd":
            return SequentialDSDSectorImage(disk)
        else:  # interleaved_dsd
            return InterleavedDSDSectorImage(disk)

    def test_implements_interface(self, sector_image):
        """All implementations are SectorImage subclasses."""
        assert isinstance(sector_image, SectorImage)

    def test_sector_size_constant(self, sector_image):
        """All implementations have 256-byte sectors."""
        assert sector_image.SECTOR_SIZE == 256

    def test_sectors_per_track_constant(self, sector_image):
        """All implementations have 10 sectors per track."""
        assert sector_image.SECTORS_PER_TRACK == 10

    def test_track_size_constant(self, sector_image):
        """All implementations have 2560-byte tracks."""
        assert sector_image.TRACK_SIZE == 2560

    def test_read_write_round_trip(self, sector_image):
        """Write then read returns same data for all implementations."""
        test_data = b"Test sector data" + b"\x00" * 240
        sector_image.write_sector(5, test_data)
        assert sector_image.read_sector(5) == test_data

    def test_multiple_sectors_independent(self, sector_image):
        """Writing to one sector doesn't affect others."""
        sector_image.write_sector(0, b"A" * 256)
        sector_image.write_sector(1, b"B" * 256)
        sector_image.write_sector(2, b"C" * 256)

        assert sector_image.read_sector(0) == b"A" * 256
        assert sector_image.read_sector(1) == b"B" * 256
        assert sector_image.read_sector(2) == b"C" * 256

"""Tests for Layer 1: Raw disk image storage."""

import pytest
from pathlib import Path
from oaknut_dfs.disk_image import DiskImage, MemoryDiskImage, FileDiskImage


class TestMemoryDiskImage:
    """Tests for MemoryDiskImage implementation."""

    def test_create_with_size(self):
        """Create a zero-filled image of specified size."""
        img = MemoryDiskImage(size=1024)
        assert img.size() == 1024
        # Verify it's zero-filled
        assert img.read_bytes(0, 1024) == bytes(1024)

    def test_create_with_data(self):
        """Create an image from existing data."""
        data = b"Hello, World!"
        img = MemoryDiskImage(data=data)
        assert img.size() == len(data)
        assert img.read_bytes(0, len(data)) == data

    def test_create_with_bytearray(self):
        """Create an image from bytearray."""
        data = bytearray(b"Test data")
        img = MemoryDiskImage(data=data)
        assert img.size() == len(data)
        assert img.read_bytes(0, len(data)) == bytes(data)

    def test_create_requires_data_or_size(self):
        """Must provide either data or size."""
        with pytest.raises(ValueError, match="Must provide either data or size"):
            MemoryDiskImage()

    def test_create_rejects_both_data_and_size(self):
        """Cannot provide both data and size."""
        with pytest.raises(ValueError, match="Provide either data or size, not both"):
            MemoryDiskImage(data=b"test", size=100)

    def test_read_bytes_at_start(self):
        """Read bytes from start of image."""
        img = MemoryDiskImage(data=b"ABCDEFGH")
        assert img.read_bytes(0, 4) == b"ABCD"

    def test_read_bytes_at_middle(self):
        """Read bytes from middle of image."""
        img = MemoryDiskImage(data=b"ABCDEFGH")
        assert img.read_bytes(2, 4) == b"CDEF"

    def test_read_bytes_at_end(self):
        """Read bytes from end of image."""
        img = MemoryDiskImage(data=b"ABCDEFGH")
        assert img.read_bytes(6, 2) == b"GH"

    def test_read_zero_bytes(self):
        """Reading zero bytes returns empty bytes."""
        img = MemoryDiskImage(size=100)
        assert img.read_bytes(50, 0) == b""

    def test_read_full_image(self):
        """Read entire image at once."""
        data = b"Test data for reading"
        img = MemoryDiskImage(data=data)
        assert img.read_bytes(0, len(data)) == data

    def test_read_negative_offset_raises(self):
        """Reading at negative offset raises ValueError."""
        img = MemoryDiskImage(size=100)
        with pytest.raises(ValueError, match="Offset cannot be negative"):
            img.read_bytes(-1, 10)

    def test_read_negative_length_raises(self):
        """Reading negative length raises ValueError."""
        img = MemoryDiskImage(size=100)
        with pytest.raises(ValueError, match="Length cannot be negative"):
            img.read_bytes(0, -1)

    def test_read_beyond_end_raises(self):
        """Reading beyond image size raises IndexError."""
        img = MemoryDiskImage(size=100)
        with pytest.raises(IndexError, match="exceeds image size"):
            img.read_bytes(90, 20)

    def test_read_exactly_at_end(self):
        """Reading exactly to the end is valid."""
        img = MemoryDiskImage(size=100)
        result = img.read_bytes(90, 10)
        assert len(result) == 10

    def test_write_bytes_at_start(self):
        """Write bytes at start of image."""
        img = MemoryDiskImage(size=100)
        img.write_bytes(0, b"HELLO")
        assert img.read_bytes(0, 5) == b"HELLO"

    def test_write_bytes_at_middle(self):
        """Write bytes in middle of image."""
        img = MemoryDiskImage(data=b"AAAAAAAAAA")
        img.write_bytes(3, b"BBB")
        assert img.read_bytes(0, 10) == b"AAABBBAAAA"

    def test_write_bytes_at_end(self):
        """Write bytes at end of image."""
        img = MemoryDiskImage(size=100)
        img.write_bytes(95, b"ABCDE")
        assert img.read_bytes(95, 5) == b"ABCDE"

    def test_write_empty_bytes(self):
        """Writing empty bytes is a no-op."""
        img = MemoryDiskImage(data=b"HELLO")
        img.write_bytes(2, b"")
        assert img.read_bytes(0, 5) == b"HELLO"

    def test_write_overwrites_existing_data(self):
        """Writing overwrites existing data."""
        img = MemoryDiskImage(data=b"HELLO WORLD")
        img.write_bytes(6, b"EARTH")
        assert img.read_bytes(0, 11) == b"HELLO EARTH"

    def test_write_negative_offset_raises(self):
        """Writing at negative offset raises ValueError."""
        img = MemoryDiskImage(size=100)
        with pytest.raises(ValueError, match="Offset cannot be negative"):
            img.write_bytes(-1, b"test")

    def test_write_beyond_end_raises(self):
        """Writing beyond image size raises IndexError."""
        img = MemoryDiskImage(size=100)
        with pytest.raises(IndexError, match="exceeds image size"):
            img.write_bytes(95, b"TOOLONG")

    def test_write_exactly_at_end(self):
        """Writing exactly to the end is valid."""
        img = MemoryDiskImage(size=100)
        img.write_bytes(95, b"ABCDE")
        assert img.read_bytes(95, 5) == b"ABCDE"

    def test_multiple_writes_and_reads(self):
        """Multiple operations maintain data integrity."""
        img = MemoryDiskImage(size=256)
        img.write_bytes(0, b"FIRST")
        img.write_bytes(100, b"SECOND")
        img.write_bytes(200, b"THIRD")

        assert img.read_bytes(0, 5) == b"FIRST"
        assert img.read_bytes(100, 6) == b"SECOND"
        assert img.read_bytes(200, 5) == b"THIRD"

    def test_resize_grow(self):
        """Growing image adds zeros."""
        img = MemoryDiskImage(data=b"HELLO")
        img.resize(10)
        assert img.size() == 10
        assert img.read_bytes(0, 5) == b"HELLO"
        assert img.read_bytes(5, 5) == bytes(5)  # New bytes are zero

    def test_resize_shrink(self):
        """Shrinking image truncates data."""
        img = MemoryDiskImage(data=b"HELLO WORLD")
        img.resize(5)
        assert img.size() == 5
        assert img.read_bytes(0, 5) == b"HELLO"

    def test_resize_to_same_size(self):
        """Resizing to same size is a no-op."""
        img = MemoryDiskImage(data=b"HELLO")
        img.resize(5)
        assert img.size() == 5
        assert img.read_bytes(0, 5) == b"HELLO"

    def test_resize_to_zero(self):
        """Can resize to zero (empty image)."""
        img = MemoryDiskImage(data=b"HELLO")
        img.resize(0)
        assert img.size() == 0

    def test_resize_negative_raises(self):
        """Resizing to negative size raises ValueError."""
        img = MemoryDiskImage(size=100)
        with pytest.raises(ValueError, match="Size cannot be negative"):
            img.resize(-1)

    def test_resize_then_write(self):
        """Can write after resizing."""
        img = MemoryDiskImage(size=10)
        img.resize(20)
        img.write_bytes(15, b"TEST")
        assert img.read_bytes(15, 4) == b"TEST"


class TestFileDiskImage:
    """Tests for FileDiskImage implementation."""

    def test_create_new_file(self, tmp_path):
        """Create a new disk image file."""
        filepath = tmp_path / "test.ssd"
        img = FileDiskImage(filepath, create=True, size=1024)

        assert img.size() == 1024
        assert filepath.exists()
        assert filepath.stat().st_size == 1024

    def test_create_requires_size(self, tmp_path):
        """Creating file requires positive size."""
        filepath = tmp_path / "test.ssd"
        with pytest.raises(ValueError, match="Size must be positive"):
            FileDiskImage(filepath, create=True, size=0)

    def test_open_existing_file(self, tmp_path):
        """Open an existing disk image file."""
        filepath = tmp_path / "existing.ssd"
        test_data = b"EXISTING DATA"
        filepath.write_bytes(test_data)

        img = FileDiskImage(filepath)
        assert img.size() == len(test_data)
        assert img.read_bytes(0, len(test_data)) == test_data

    def test_open_nonexistent_file_raises(self, tmp_path):
        """Opening non-existent file raises FileNotFoundError."""
        filepath = tmp_path / "nonexistent.ssd"
        with pytest.raises(FileNotFoundError):
            FileDiskImage(filepath)

    def test_read_bytes_from_file(self, tmp_path):
        """Read bytes from file-backed image."""
        filepath = tmp_path / "test.ssd"
        test_data = b"ABCDEFGHIJKLMNOP"
        filepath.write_bytes(test_data)

        img = FileDiskImage(filepath)
        assert img.read_bytes(5, 5) == b"FGHIJ"

    def test_write_bytes_to_file(self, tmp_path):
        """Write bytes to file-backed image."""
        filepath = tmp_path / "test.ssd"
        filepath.write_bytes(b"X" * 100)

        img = FileDiskImage(filepath)
        img.write_bytes(10, b"HELLO")

        # Verify by reading back
        assert img.read_bytes(10, 5) == b"HELLO"

        # Verify file was actually modified
        with open(filepath, "rb") as f:
            f.seek(10)
            assert f.read(5) == b"HELLO"

    def test_write_persists_across_instances(self, tmp_path):
        """Writes persist when reopening file."""
        filepath = tmp_path / "test.ssd"
        filepath.write_bytes(b"X" * 100)

        # Write with first instance
        img1 = FileDiskImage(filepath)
        img1.write_bytes(20, b"PERSISTED")

        # Read with second instance
        img2 = FileDiskImage(filepath)
        assert img2.read_bytes(20, 9) == b"PERSISTED"

    def test_read_negative_offset_raises(self, tmp_path):
        """Reading at negative offset raises ValueError."""
        filepath = tmp_path / "test.ssd"
        filepath.write_bytes(b"X" * 100)

        img = FileDiskImage(filepath)
        with pytest.raises(ValueError, match="Offset cannot be negative"):
            img.read_bytes(-1, 10)

    def test_read_negative_length_raises(self, tmp_path):
        """Reading negative length raises ValueError."""
        filepath = tmp_path / "test.ssd"
        filepath.write_bytes(b"X" * 100)

        img = FileDiskImage(filepath)
        with pytest.raises(ValueError, match="Length cannot be negative"):
            img.read_bytes(0, -1)

    def test_read_beyond_end_raises(self, tmp_path):
        """Reading beyond file size raises IndexError."""
        filepath = tmp_path / "test.ssd"
        filepath.write_bytes(b"X" * 100)

        img = FileDiskImage(filepath)
        with pytest.raises(IndexError, match="exceeds image size"):
            img.read_bytes(90, 20)

    def test_write_negative_offset_raises(self, tmp_path):
        """Writing at negative offset raises ValueError."""
        filepath = tmp_path / "test.ssd"
        filepath.write_bytes(b"X" * 100)

        img = FileDiskImage(filepath)
        with pytest.raises(ValueError, match="Offset cannot be negative"):
            img.write_bytes(-1, b"test")

    def test_write_beyond_end_raises(self, tmp_path):
        """Writing beyond file size raises IndexError."""
        filepath = tmp_path / "test.ssd"
        filepath.write_bytes(b"X" * 100)

        img = FileDiskImage(filepath)
        with pytest.raises(IndexError, match="exceeds image size"):
            img.write_bytes(95, b"TOOLONG")

    def test_resize_grow_file(self, tmp_path):
        """Growing file adds zeros."""
        filepath = tmp_path / "test.ssd"
        filepath.write_bytes(b"HELLO")

        img = FileDiskImage(filepath)
        img.resize(10)

        assert img.size() == 10
        assert img.read_bytes(0, 5) == b"HELLO"
        assert img.read_bytes(5, 5) == bytes(5)

    def test_resize_shrink_file(self, tmp_path):
        """Shrinking file truncates data."""
        filepath = tmp_path / "test.ssd"
        filepath.write_bytes(b"HELLO WORLD")

        img = FileDiskImage(filepath)
        img.resize(5)

        assert img.size() == 5
        assert img.read_bytes(0, 5) == b"HELLO"

    def test_resize_negative_raises(self, tmp_path):
        """Resizing to negative size raises ValueError."""
        filepath = tmp_path / "test.ssd"
        filepath.write_bytes(b"X" * 100)

        img = FileDiskImage(filepath)
        with pytest.raises(ValueError, match="Size cannot be negative"):
            img.resize(-1)

    def test_multiple_operations(self, tmp_path):
        """Multiple operations maintain data integrity."""
        filepath = tmp_path / "test.ssd"
        img = FileDiskImage(filepath, create=True, size=256)

        img.write_bytes(0, b"FIRST")
        img.write_bytes(100, b"SECOND")
        img.write_bytes(200, b"THIRD")

        assert img.read_bytes(0, 5) == b"FIRST"
        assert img.read_bytes(100, 6) == b"SECOND"
        assert img.read_bytes(200, 5) == b"THIRD"


class TestDiskImageInterface:
    """Tests verifying both implementations conform to DiskImage interface."""

    @pytest.fixture(params=["memory", "file"])
    def disk_image(self, request, tmp_path):
        """Parameterized fixture providing both implementations."""
        if request.param == "memory":
            return MemoryDiskImage(size=1024)
        else:  # file
            filepath = tmp_path / "test.img"
            return FileDiskImage(filepath, create=True, size=1024)

    def test_implements_interface(self, disk_image):
        """Both implementations are DiskImage subclasses."""
        assert isinstance(disk_image, DiskImage)

    def test_read_write_round_trip(self, disk_image):
        """Write then read returns same data."""
        test_data = b"Test data for round trip"
        disk_image.write_bytes(100, test_data)
        result = disk_image.read_bytes(100, len(test_data))
        assert result == test_data

    def test_size_method(self, disk_image):
        """Size method returns correct value."""
        assert disk_image.size() == 1024

    def test_resize_method(self, disk_image):
        """Resize method works correctly."""
        disk_image.resize(2048)
        assert disk_image.size() == 2048

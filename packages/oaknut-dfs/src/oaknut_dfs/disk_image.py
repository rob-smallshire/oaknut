"""Layer 1: Raw disk image storage abstraction."""

from abc import ABC, abstractmethod
from pathlib import Path


class DiskImage(ABC):
    """Abstract base class for raw disk image storage."""

    @abstractmethod
    def read_bytes(self, offset: int, length: int) -> bytes:
        """
        Read bytes at physical offset.

        Args:
            offset: Byte offset from start of image
            length: Number of bytes to read

        Returns:
            Bytes read from image

        Raises:
            ValueError: If offset or length is negative
            IndexError: If read extends beyond image size
        """
        pass

    @abstractmethod
    def write_bytes(self, offset: int, data: bytes) -> None:
        """
        Write bytes at physical offset.

        Args:
            offset: Byte offset from start of image
            data: Bytes to write

        Raises:
            ValueError: If offset is negative
            IndexError: If write extends beyond image size
        """
        pass

    @abstractmethod
    def size(self) -> int:
        """
        Get total size of image in bytes.

        Returns:
            Size in bytes
        """
        pass

    @abstractmethod
    def resize(self, new_size: int) -> None:
        """
        Resize the image.

        Args:
            new_size: New size in bytes

        Raises:
            ValueError: If new_size is negative
        """
        pass


class MemoryDiskImage(DiskImage):
    """In-memory disk image implementation using bytearray."""

    def __init__(self, data: bytes | bytearray | None = None, size: int = 0):
        """
        Create an in-memory disk image.

        Args:
            data: Initial data (creates zero-filled image if None)
            size: Size in bytes if data is None

        Raises:
            ValueError: If both data and size are provided, or neither
        """
        if data is not None and size != 0:
            raise ValueError("Provide either data or size, not both")
        if data is None and size == 0:
            raise ValueError("Must provide either data or size")

        if data is not None:
            self._data = bytearray(data)
        else:
            self._data = bytearray(size)

    def read_bytes(self, offset: int, length: int) -> bytes:
        """Read bytes at physical offset."""
        if offset < 0:
            raise ValueError(f"Offset cannot be negative: {offset}")
        if length < 0:
            raise ValueError(f"Length cannot be negative: {length}")
        if offset + length > len(self._data):
            raise IndexError(
                f"Read at offset {offset} with length {length} "
                f"exceeds image size {len(self._data)}"
            )
        return bytes(self._data[offset : offset + length])

    def write_bytes(self, offset: int, data: bytes) -> None:
        """Write bytes at physical offset."""
        if offset < 0:
            raise ValueError(f"Offset cannot be negative: {offset}")
        if offset + len(data) > len(self._data):
            raise IndexError(
                f"Write at offset {offset} with {len(data)} bytes "
                f"exceeds image size {len(self._data)}"
            )
        self._data[offset : offset + len(data)] = data

    def size(self) -> int:
        """Get total size of image in bytes."""
        return len(self._data)

    def resize(self, new_size: int) -> None:
        """
        Resize the image.

        If growing, new bytes are zero-filled.
        If shrinking, data beyond new_size is discarded.
        """
        if new_size < 0:
            raise ValueError(f"Size cannot be negative: {new_size}")

        current_size = len(self._data)
        if new_size > current_size:
            # Grow - add zeros
            self._data.extend(bytes(new_size - current_size))
        elif new_size < current_size:
            # Shrink - truncate
            self._data = self._data[:new_size]


class FileDiskImage(DiskImage):
    """File-backed disk image implementation."""

    def __init__(self, filepath: Path | str, create: bool = False, size: int = 0):
        """
        Open or create a file-backed disk image.

        Args:
            filepath: Path to disk image file
            create: Create new file if it doesn't exist
            size: Initial size if creating new file

        Raises:
            FileNotFoundError: If file doesn't exist and create=False
            ValueError: If create=True but size=0
        """
        self._filepath = Path(filepath)

        if create:
            if size <= 0:
                raise ValueError("Size must be positive when creating file")
            # Create new file with specified size
            with open(self._filepath, "wb") as f:
                f.write(bytes(size))
        else:
            if not self._filepath.exists():
                raise FileNotFoundError(f"File not found: {self._filepath}")

        # Cache size to avoid repeated stat calls
        self._size = self._filepath.stat().st_size

    def read_bytes(self, offset: int, length: int) -> bytes:
        """Read bytes at physical offset."""
        if offset < 0:
            raise ValueError(f"Offset cannot be negative: {offset}")
        if length < 0:
            raise ValueError(f"Length cannot be negative: {length}")
        if offset + length > self._size:
            raise IndexError(
                f"Read at offset {offset} with length {length} "
                f"exceeds image size {self._size}"
            )

        with open(self._filepath, "rb") as f:
            f.seek(offset)
            return f.read(length)

    def write_bytes(self, offset: int, data: bytes) -> None:
        """Write bytes at physical offset."""
        if offset < 0:
            raise ValueError(f"Offset cannot be negative: {offset}")
        if offset + len(data) > self._size:
            raise IndexError(
                f"Write at offset {offset} with {len(data)} bytes "
                f"exceeds image size {self._size}"
            )

        with open(self._filepath, "r+b") as f:
            f.seek(offset)
            f.write(data)

    def size(self) -> int:
        """Get total size of image in bytes."""
        return self._size

    def resize(self, new_size: int) -> None:
        """Resize the file."""
        if new_size < 0:
            raise ValueError(f"Size cannot be negative: {new_size}")

        with open(self._filepath, "r+b") as f:
            f.truncate(new_size)

        self._size = new_size

"""Shared pytest fixtures for reference image tests."""

import pytest
import shutil
import stat
from pathlib import Path

# Import to ensure catalogue classes are registered
import oaknut_dfs.acorn_dfs_catalogue  # noqa: F401

from oaknut_dfs import DFS
from oaknut_dfs.formats import (
    ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_40T_SINGLE_SIDED,
    ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_80T_SINGLE_SIDED,
    DiskFormat,
)


# Path to reference images directory
REFERENCE_IMAGES = Path(__file__).parent / "data" / "images"


def _detect_disk_format(filepath: Path) -> DiskFormat:
    """Detect disk format from file extension and size."""
    size = filepath.stat().st_size
    ext = filepath.suffix.lower()

    if ext == ".ssd":
        if size == 102400:  # 40 tracks × 10 sectors × 256 bytes
            return ACORN_DFS_40T_SINGLE_SIDED
        elif size == 204800:  # 80 tracks × 10 sectors × 256 bytes
            return ACORN_DFS_80T_SINGLE_SIDED
    elif ext == ".dsd":
        if size == 204800:  # 40 tracks × 2 sides × 10 sectors × 256 bytes (interleaved)
            return ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED
        elif size == 409600:  # 80 tracks × 2 sides × 10 sectors × 256 bytes (interleaved)
            return ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED

    raise ValueError(
        f"Unknown disk format for {filepath.name}: size={size}, ext={ext}"
    )


@pytest.fixture
def reference_image(tmp_path):
    """Load a reference disk image.

    Returns a factory function that loads reference images using DFS.from_buffer().
    Creates a temporary copy to prevent accidental modification of originals.

    Usage:
        def test_something(reference_image):
            disk = reference_image("01-basic-validation.ssd")
            # disk is a DFS instance from a temp copy

            # For double-sided disks:
            disk0 = reference_image("04-double-sided.dsd", side=0)
            disk1 = reference_image("04-double-sided.dsd", side=1)

    Args:
        reference_name: Image filename (e.g., "01-basic-validation.ssd")
        side: For DSD images, which side to access (0 or 1)

    Returns:
        DFS instance for the specified image/side
    """

    def _open(reference_name: str, side: int = 0) -> DFS:
        src_path = REFERENCE_IMAGES / reference_name
        if not src_path.exists():
            pytest.skip(f"Reference image not found: {reference_name}")

        # Create unique tmp copy (unique per test to avoid conflicts)
        # Use side in filename to avoid collisions when same image used for multiple sides
        tmp_copy = tmp_path / f"{reference_name}.side{side}.tmp"

        # Only copy if it doesn't already exist
        if not tmp_copy.exists():
            shutil.copy2(src_path, tmp_copy)
            # Make the copy writable for pytest cleanup
            tmp_copy.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

        # Read into buffer
        buffer = tmp_copy.read_bytes()

        # Detect format and create DFS
        disk_format = _detect_disk_format(src_path)
        return DFS.from_buffer(memoryview(buffer), disk_format, side=side)

    return _open


@pytest.fixture
def writable_copy(tmp_path):
    """Create a writable copy of a reference disk image.

    Returns a factory function that creates temporary writable copies.

    Usage:
        def test_something(writable_copy):
            disk, path = writable_copy("03-fragmented.ssd")
            # disk is a DFS instance, path is the temp file location
            disk.save("$.NEW", b"data")  # OK - working on copy

    Args:
        reference_name: Image filename
        side: For DSD images, which side to access (0 or 1)

    Returns:
        Tuple of (DFS instance, Path to temp file)
    """

    def _copy(reference_name: str, side: int = 0) -> tuple[DFS, Path]:
        src_path = REFERENCE_IMAGES / reference_name
        if not src_path.exists():
            pytest.skip(f"Reference image not found: {reference_name}")

        # Create writable copy
        dst_path = tmp_path / reference_name
        shutil.copy2(src_path, dst_path)
        dst_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

        # Read into buffer
        buffer = bytearray(dst_path.read_bytes())

        # Detect format and create DFS
        disk_format = _detect_disk_format(src_path)
        dfs = DFS.from_buffer(memoryview(buffer), disk_format, side=side)

        return dfs, dst_path

    return _copy

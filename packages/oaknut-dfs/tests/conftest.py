"""Shared pytest fixtures for reference image tests."""

import pytest
import shutil
import stat
from pathlib import Path


# Path to reference images directory
REFERENCE_IMAGES = Path(__file__).parent / "data" / "images"


@pytest.fixture
def writable_copy(tmp_path):
    """Create a writable copy of a reference disk image.

    Usage:
        def test_something(writable_copy):
            disk_path = writable_copy("01-basic-validation.ssd")
            # disk_path is now a writable copy in tmp_path
            disk = DFSImage.open(disk_path)
            disk.save("$.NEW", b"data")  # OK - working on copy
    """
    def _copy(reference_name: str) -> Path:
        src = REFERENCE_IMAGES / reference_name
        if not src.exists():
            pytest.skip(f"Reference image not found: {reference_name}")

        dst = tmp_path / reference_name
        shutil.copy2(src, dst)

        # Make the copy writable (copy2 preserves read-only permissions)
        dst.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

        return dst

    return _copy


@pytest.fixture
def reference_image():
    """Load a reference disk image in read-only mode.

    Usage:
        def test_something(reference_image):
            disk = reference_image("01-basic-validation.ssd")
            # disk is opened read-only

            # For double-sided disks:
            disk0 = reference_image("04-double-sided.dsd", side=0)
            disk1 = reference_image("04-double-sided.dsd", side=1)
    """
    def _open(reference_name: str, writable: bool = False, side: int = 0):
        from oaknut_dfs.dfs_filesystem import DFSImage

        disk_path = REFERENCE_IMAGES / reference_name
        if not disk_path.exists():
            pytest.skip(f"Reference image not found: {reference_name}")

        return DFSImage.open(disk_path, writable=writable, side=side)

    return _open

#!/usr/bin/env python3
"""Test create() method."""

import sys
import tempfile
import os
sys.path.insert(0, 'src')

from oaknut_dfs import DFSImage

# Create a temporary filename (but don't create the file yet)
temp_dir = tempfile.gettempdir()
temp_path = os.path.join(temp_dir, f'test_{os.getpid()}.ssd')

try:
    print(f"Creating disk at {temp_path}")

    # Use create() context manager
    with DFSImage.create(temp_path, title="TEST", num_tracks_per_side=40) as disk:
        print(f"Disk title: {disk.title}")
        print(f"Free sectors: {disk.free_sectors}")
        print(f"Total sectors: {disk.info.num_sectors}")

        # Save a file
        test_data = b"Hello, World! " * 100
        print(f"\nSaving {len(test_data)} bytes...")
        disk.save("$.TEST", test_data)

        print(f"Files: {len(disk.files)}")
        print(f"Free sectors after save: {disk.free_sectors}")

    # Open and read back
    print("\nOpening disk again...")
    with DFSImage.open(temp_path, mode="rb") as disk:
        print(f"Files on disk: {len(disk.files)}")
        loaded = disk.load("$.TEST")
        print(f"Loaded {len(loaded)} bytes")
        assert loaded == test_data
        print("✓ Data matches!")

finally:
    os.unlink(temp_path)

print("\n✓ Test passed!")

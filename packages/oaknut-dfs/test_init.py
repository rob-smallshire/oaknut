#!/usr/bin/env python3
"""Debug disk initialization."""

import sys
sys.path.insert(0, 'src')

from oaknut_dfs import DFSImage

# Create a disk image in memory
buffer = bytearray(204800)  # 200KB disk = 800 sectors
disk = DFSImage(buffer, format="ssd")

print("Before setting title:")
info = disk.info
print(f"Title: '{info.title}'")
print(f"Num files: {info.num_files}")
print(f"Total sectors: {info.total_sectors}")
print(f"Free sectors: {disk.free_sectors}")

# Set title
disk.title = "TEST"

print("\nAfter setting title:")
info = disk.info
print(f"Title: '{info.title}'")
print(f"Num files: {info.num_files}")
print(f"Total sectors: {info.total_sectors}")
print(f"Free sectors: {disk.free_sectors}")

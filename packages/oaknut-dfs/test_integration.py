#!/usr/bin/env python3
"""Quick integration test of DFS load/save with SectorsView."""

import sys
sys.path.insert(0, 'src')

from oaknut_dfs import DFSImage

# Test: Create disk, save file, load file
print("Integration Test: save and load with SectorsView")
print("=" * 50)

# Create a disk image in memory
buffer = bytearray(204800)  # 200KB disk
disk = DFSImage(buffer, format="ssd")

# Initialize the disk
disk.title = "TEST"

print(f"Disk title: {disk.title}")
print(f"Free sectors: {disk.free_sectors}")

# Save a file
test_data = b"Hello, World! " * 100  # 1400 bytes
print(f"\nSaving {len(test_data)} bytes to $.TEST...")
disk.save("$.TEST", test_data, load_address=0x1900, exec_address=0x1900)

print(f"Files on disk: {len(disk.files)}")
print(f"Free sectors after save: {disk.free_sectors}")

# Load the file back
print("\nLoading $.TEST...")
loaded_data = disk.load("$.TEST")

# Verify
print(f"Loaded {len(loaded_data)} bytes")
assert len(loaded_data) == len(test_data), f"Length mismatch: {len(loaded_data)} != {len(test_data)}"
assert loaded_data == test_data, "Data mismatch!"

# Check file info
info = disk.get_file_info("$.TEST")
print(f"Load address: 0x{info.load_address:04X}")
print(f"Exec address: 0x{info.exec_address:04X}")
assert info.load_address == 0x1900
assert info.exec_address == 0x1900

# Test multiple files
print("\n" + "=" * 50)
print("Testing multiple files...")

for i in range(5):
    filename = f"$.FILE{i}"
    data = f"File {i} contents\n".encode() * 10
    disk.save(filename, data)
    print(f"Saved {filename}: {len(data)} bytes")

print(f"\nTotal files: {len(disk.files)}")
print(f"Free sectors: {disk.free_sectors}")

# Load and verify each file
for i in range(5):
    filename = f"$.FILE{i}"
    loaded = disk.load(filename)
    expected = f"File {i} contents\n".encode() * 10
    assert loaded == expected, f"{filename} data mismatch!"
    print(f"Verified {filename}")

print("\n" + "=" * 50)
print("✓ All integration tests passed!")
print("✓ SectorsView correctly handles multi-sector file I/O")
